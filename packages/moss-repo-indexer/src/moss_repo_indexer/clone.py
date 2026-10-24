"""Resolve a local path or shallow-clone a git URL into a working directory."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_GIT_SSH_RE = re.compile(r"^git@[^:]+:.+\.git$")
_GIT_URL_RE = re.compile(r"^(https?|git)://", re.IGNORECASE)


@dataclass
class ResolvedSource:
    root: Path
    repo_name: str
    ref: str | None
    cleanup: bool

    def close(self) -> None:
        if self.cleanup and self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)


def resolve_source(source: str, ref: str | None = None) -> ResolvedSource:
    """Return a local directory for `source` (filesystem path or git URL)."""
    stripped = source.strip()
    if _is_git_url(stripped):
        return _clone_git_url(stripped, ref)
    return _resolve_local_path(stripped, ref)


def _is_git_url(source: str) -> bool:
    if _GIT_SSH_RE.match(source) or _GIT_URL_RE.match(source):
        return True
    if source.endswith(".git") and "://" in source:
        return True
    return False


def _resolve_local_path(source: str, ref: str | None) -> ResolvedSource:
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Source path is not a directory: {root}")
    return ResolvedSource(
        root=root,
        repo_name=root.name,
        ref=ref,
        cleanup=False,
    )


def _clone_git_url(url: str, ref: str | None) -> ResolvedSource:
    if shutil.which("git") is None:
        raise RuntimeError("git is required to clone a repository URL")

    temp_dir = Path(tempfile.mkdtemp(prefix="moss-repo-"))
    try:
        _run_git_clone(url, temp_dir, ref)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return ResolvedSource(
        root=temp_dir,
        repo_name=_repo_name_from_url(url),
        ref=ref,
        cleanup=True,
    )


def _run_git_clone(url: str, dest: Path, ref: str | None) -> None:
    command = ["git", "clone", "--depth", "1"]
    if ref:
        command.extend(["--branch", ref])
    command.extend([url, str(dest)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git clone failed").strip()
        raise RuntimeError(f"Failed to clone {url}: {detail}")


def _repo_name_from_url(url: str) -> str:
    if _GIT_SSH_RE.match(url):
        name = url.rsplit(":", 1)[-1]
    else:
        name = urlparse(url).path
    name = Path(name).name
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repo"
