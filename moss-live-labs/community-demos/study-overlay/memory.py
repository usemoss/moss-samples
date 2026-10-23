from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from settings import load_settings


LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent
SIDECAR = ROOT / "moss_sidecar.mjs"
BUNDLED_NODE = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"


@dataclass
class MemoryResult:
    context: str
    used: bool
    warning: str = ""


def title_from_explanation(text: str) -> str:
    cleaned = re.sub(r"[$#*_`>\-]+", " ", text).strip()
    first_line = next((line.strip() for line in cleaned.splitlines() if line.strip()), "Study note")
    words = first_line.split()
    return " ".join(words[:10]) or "Study note"


def _run(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(value)

        future = asyncio.run_coroutine_threadsafe(value, loop)
        return future.result()
    return value


class MossPythonBackend:
    name = "moss-python"

    def __init__(self, project_id: str, project_key: str, session_name: str) -> None:
        from moss import MossClient

        self._moss = __import__("moss")
        self.client = MossClient(project_id, project_key)
        try:
            self.session = _run(self.client.session(index_name=session_name))
        except TypeError:
            self.session = _run(self.client.session(session_name))

    def query(self, query: str, top_k: int) -> list[dict[str, Any]]:
        try:
            options = self._moss.QueryOptions(top_k=top_k)
        except Exception:
            options = {"top_k": top_k}

        try:
            result = _run(self.session.query(query, options))
        except TypeError:
            result = _run(self.session.query(query, top_k=top_k))

        docs = getattr(result, "docs", None)
        if docs is None and isinstance(result, dict):
            docs = result.get("docs") or result.get("documents")
        if docs is None:
            docs = result if isinstance(result, list) else []

        normalized = []
        for doc in docs:
            normalized.append(
                {
                    "id": getattr(doc, "id", None) or (doc.get("id") if isinstance(doc, dict) else None),
                    "score": getattr(doc, "score", None) or (doc.get("score") if isinstance(doc, dict) else None),
                    "text": getattr(doc, "text", None) or (doc.get("text") if isinstance(doc, dict) else str(doc)),
                }
            )
        return normalized

    def add_docs(self, docs: list[dict[str, Any]]) -> None:
        document_info = self._moss.DocumentInfo
        moss_docs = []
        for doc in docs:
            try:
                moss_docs.append(document_info(id=doc["id"], text=doc["text"], metadata=doc.get("metadata")))
            except TypeError:
                moss_docs.append(document_info(id=doc["id"], text=doc["text"]))
        _run(self.session.add_docs(moss_docs))

    def close(self) -> None:
        return


class MossJsBackend:
    name = "moss-js"

    def __init__(self, project_id: str, project_key: str, session_name: str) -> None:
        node = self._node_path()
        if not node:
            raise RuntimeError("Node.js was not found. Install Node or set STUDYOVERLAY_NODE.")
        if not SIDECAR.exists():
            raise RuntimeError(f"Moss sidecar missing at {SIDECAR}")

        self._next_id = 0
        self._lock = threading.Lock()
        self._process = subprocess.Popen(
            [node, str(SIDECAR)],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._request(
            {
                "action": "init",
                "projectId": project_id,
                "projectKey": project_key,
                "sessionName": session_name,
            },
            timeout=45,
        )

    def _node_path(self) -> str:
        candidates = [
            os.environ.get("STUDYOVERLAY_NODE"),
            shutil.which("node"),
            str(BUNDLED_NODE) if BUNDLED_NODE.exists() else "",
        ]
        return next((candidate for candidate in candidates if candidate), "")

    def _drain_stderr(self) -> None:
        if not self._process.stderr:
            return
        for line in self._process.stderr:
            LOGGER.warning("Moss sidecar: %s", line.rstrip())

    def _request(self, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
        with self._lock:
            if self._process.poll() is not None:
                raise RuntimeError(f"Moss sidecar exited with code {self._process.returncode}")
            self._next_id += 1
            payload["id"] = self._next_id
            assert self._process.stdin is not None
            assert self._process.stdout is not None
            self._process.stdin.write(json.dumps(payload) + "\n")
            self._process.stdin.flush()

            deadline = time.time() + timeout
            while time.time() < deadline:
                line = self._process.stdout.readline()
                if not line:
                    if self._process.poll() is not None:
                        raise RuntimeError(f"Moss sidecar exited with code {self._process.returncode}")
                    continue
                response = json.loads(line)
                if response.get("id") != payload["id"]:
                    continue
                if not response.get("ok"):
                    raise RuntimeError(response.get("error", "Moss sidecar request failed"))
                return response.get("data") or {}

        raise TimeoutError("Moss sidecar timed out.")

    def query(self, query: str, top_k: int) -> list[dict[str, Any]]:
        data = self._request({"action": "query", "query": query, "topK": top_k})
        return list(data.get("docs") or [])

    def add_docs(self, docs: list[dict[str, Any]]) -> None:
        self._request({"action": "add_docs", "docs": docs})

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()


class StudyMemory:
    def __init__(self) -> None:
        self.enabled = False
        self.warning = ""
        self.backend: MossJsBackend | MossPythonBackend | None = None
        self._init()

    def _init(self) -> None:
        settings = load_settings()
        project_id = settings.get("MOSS_PROJECT_ID", "").strip()
        project_key = settings.get("MOSS_PROJECT_KEY", "").strip()
        if not project_id or not project_key:
            self.warning = "Moss credentials are missing; semantic memory is disabled."
            LOGGER.warning(self.warning)
            return

        backend_order = os.environ.get("STUDYOVERLAY_MOSS_BACKEND", "js,python").split(",")
        errors = []
        for backend_name in [name.strip().lower() for name in backend_order if name.strip()]:
            try:
                if backend_name == "js":
                    self.backend = MossJsBackend(project_id, project_key, "study-session")
                elif backend_name == "python":
                    self.backend = MossPythonBackend(project_id, project_key, "study-session")
                else:
                    continue
                self.enabled = True
                self.warning = ""
                LOGGER.info("Moss memory enabled via %s.", self.backend.name)
                return
            except Exception as exc:
                errors.append(f"{backend_name}: {exc}")

        self.warning = "Moss memory disabled: " + " | ".join(errors)
        LOGGER.warning(self.warning)

    def reload(self) -> None:
        if self.backend:
            self.backend.close()
        self.enabled = False
        self.warning = ""
        self.backend = None
        self._init()

    def related_context(self, query: str, top_k: int = 3) -> MemoryResult:
        if not self.enabled or self.backend is None:
            return MemoryResult("", False, self.warning)

        try:
            docs = self.backend.query(query, top_k)[:top_k]
            snippets = []
            for index, doc in enumerate(docs, 1):
                text = str(doc.get("text") or "").strip()
                if text:
                    snippets.append(f"{index}. {text[:700]}")
            return MemoryResult("\n".join(snippets), bool(snippets), "")
        except Exception as exc:
            warning = f"Moss query skipped: {exc}"
            LOGGER.warning(warning)
            return MemoryResult("", False, warning)

    def remember(self, explanation: str, topic: str | None = None) -> None:
        if not self.enabled or self.backend is None or not explanation.strip():
            return

        title = topic or title_from_explanation(explanation)
        doc_id = f"explanation-{int(time.time() * 1000)}"
        text = f"{title}\n\n{explanation}"
        try:
            self.backend.add_docs(
                [
                    {
                        "id": doc_id,
                        "text": text,
                        "metadata": {"title": title, "source": "studyoverlay"},
                    }
                ]
            )
        except Exception as exc:
            LOGGER.warning("Moss add_docs skipped: %s", exc)
