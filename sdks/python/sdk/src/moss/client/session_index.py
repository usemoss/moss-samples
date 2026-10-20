from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

from moss_core import (
    AddDocumentsOptions as _RustAddDocumentsOptions,
    Chunking,
    DocumentInfo,
    GetDocumentsOptions,
    InvalidArgumentError,
    MutationOptions,
    QueryOptions,
    SearchResult,
    SessionIndex as _RustSessionIndex,
    PushIndexResult,
    to_document_infos,
)

from .docs_input import Chunker, DocsInput, reject_chunking_for_custom


class SessionIndex:
    """
    A local in-session index for real-time indexing and querying.

    All operations (add_docs, delete_docs, query) run entirely in-memory
    with no cloud round trips. Call push_index() at session end to persist
    the index to the cloud for bookkeeping and future retrieval.

    Usage telemetry is tracked and reported automatically in the background.
    Call close(), or use the session as a context manager, to send the final
    report and free the session's memory.

    Example:
        ```python
        # Auto-loads from cloud if the index exists, starts fresh if not
        async with await client.session(index_name="session-abc") as session:
            await session.add_docs([DocumentInfo(id="1", text="Customer asked about billing")])
            results = await session.query("billing question")

            result = await session.push_index()
            # optionally: await client.get_job_status(result.job_id)
        ```
    """

    def __init__(self, name: str, model_id: str, _inner: "_RustSessionIndex") -> None:
        # The core holds the name and the model, and a load can change the model.
        self._inner = _inner
        self._client_cache_path: Optional[str] = None

    @classmethod
    def _create(
        cls,
        name: str,
        model_id: str,
        project_id: str,
        project_key: str,
        client_id: Optional[str] = None,
        artifact_version: Optional[str] = None,
        manifest_sha256: Optional[str] = None,
        client_cache_path: Optional[str] = None,
    ) -> "SessionIndex":
        # Provenance is a pair: a version without its authoritative manifest
        # digest (or vice versa) certifies nothing. The native constructor
        # already refuses the incomplete pair, but it can only describe the
        # positional argument it received, so name the Python keywords here.
        # Mirrors the JavaScript binding's boundary check.
        if (artifact_version is None) != (manifest_sha256 is None):
            missing, provided = (
                ("manifest_sha256", "artifact_version")
                if manifest_sha256 is None
                else ("artifact_version", "manifest_sha256")
            )
            raise ValueError(
                f"session() requires {missing} whenever {provided} is given: a model "
                "artifact version and its manifest SHA-256 are a single identity and "
                "neither half certifies anything on its own."
            )

        if artifact_version is None and manifest_sha256 is None:
            inner = _RustSessionIndex(name, model_id, project_id, project_key, client_id)
        else:
            inner = _RustSessionIndex(
                name,
                model_id,
                project_id,
                project_key,
                client_id,
                artifact_version,
                manifest_sha256,
            )
        session = cls(name, model_id, inner)
        session._client_cache_path = client_cache_path
        return session

    @property
    def name(self) -> str:
        """The index name."""
        return self._inner.name

    @property
    def doc_count(self) -> int:
        """Number of documents in the local session index."""
        return self._inner.doc_count

    @property
    def model_id(self) -> str:
        """
        The embedding model this session uses, or `"custom"`.

        A load moves the session to the loaded model.
        The value is as of the last completed call, so reading it
        never waits for a call in progress, and it still reads after `close()`.
        """
        return self._inner.model_id

    async def add_docs(
        self,
        docs: DocsInput,
        options: Optional[MutationOptions] = None,
        *,
        chunker: Optional[Chunker] = None,
        chunking: Optional[Chunking] = None,
    ) -> Tuple[int, int]:
        """
        Add or update documents in the local session index.

        Embeddings are generated locally via Rust core, with no cloud round trip.

        Args:
            docs: `DocumentInfo` objects, dicts, JSON array or JSON Lines text, or file
                  paths, as in `MossClient.create_index`. When using model_id='custom',
                  each doc must have an embedding.
            options: Mutation options (e.g. upsert behavior).
            chunker: Splits each document's text into chunks before indexing.
            chunking: A `Chunking` that chunks with bounded native options instead (it also
                  chunks `DocumentInfo`, dict and JSON input); pass `chunker` or `chunking`, not both.

        Returns:
            Tuple of (added_count, updated_count).
        """
        reject_chunking_for_custom(chunker, chunking, self.model_id)
        resolved_docs = await asyncio.to_thread(to_document_infos, docs, chunker, chunking)
        rust_opts = None
        if options is not None:
            upsert = bool(options.upsert) if options.upsert is not None else True
            rust_opts = _RustAddDocumentsOptions(upsert=upsert)
        if self.model_id == "custom":
            embeddings = self._get_custom_embeddings(resolved_docs)
            return await asyncio.to_thread(
                self._inner.add_docs,
                resolved_docs,
                embeddings,
                rust_opts,
            )
        return await asyncio.to_thread(self._inner.add_docs_text, resolved_docs, rust_opts)

    async def delete_docs(self, doc_ids: List[str]) -> int:
        """
        Delete documents from the local session index by their IDs.

        Returns:
            Number of documents deleted.
        """
        return await asyncio.to_thread(self._inner.delete_docs, doc_ids)

    async def get_docs(
        self,
        options: Optional[GetDocumentsOptions] = None,
    ) -> List[DocumentInfo]:
        """Retrieve documents from the local session index."""
        return await asyncio.to_thread(self._inner.get_docs, options)

    async def query(
        self,
        query: str,
        options: Optional[QueryOptions] = None,
    ) -> SearchResult:
        """
        Perform a semantic search over the local session index.

        Runs entirely in-memory (~1-10ms). No cloud call.

        A blank `query` (empty or only whitespace) with no
        `options.embedding` returns no results at every `alpha`, without
        running the embedding model. With an embedding, a blank `query` ranks
        by the embedding alone. A custom-model session still needs
        `options.embedding`.

        Args:
            query: The search query text.
            options: Query options (top_k, alpha, embedding, filter). top_k
                defaults to 5, and 0 returns no results. Example filter:
                QueryOptions(filter={"$and": [
                    {"field": "type", "condition": {"$eq": "faq"}},
                    {"field": "priority", "condition": {"$gt": "5"}},
                ]})

        Returns:
            SearchResult with scored documents.
        """
        top_k = getattr(options, "top_k", None)
        top_k = top_k if top_k is not None else 5
        alpha = getattr(options, "alpha", None)
        alpha = alpha if alpha is not None else 0.8
        query_embedding = getattr(options, "embedding", None)
        filter = getattr(options, "filter", None)
        group_by = getattr(options, "group_by", None)

        if query_embedding is None:
            if self.model_id == "custom":
                raise InvalidArgumentError(
                    "This session uses custom embeddings. "
                    "Provide a query embedding via QueryOptions.embedding."
                )
            return await asyncio.to_thread(
                self._inner.query_text,
                query,
                top_k,
                alpha,
                filter,
                group_by,
            )

        return await asyncio.to_thread(
            self._inner.query,
            query,
            top_k,
            list(query_embedding),
            alpha,
            filter,
            group_by,
        )

    async def push_index(self) -> PushIndexResult:
        """
        Push the local session index to the cloud.

        The cloud index is created or replaced if one already exists with the
        same name. A custom-model session keeps its locally-computed
        embeddings; for a built-in model the server re-embeds the text with
        that model, so the index loads and answers text queries like one built
        with `create_index`.

        Returns:
            PushIndexResult with job_id and status.
        """
        return await asyncio.to_thread(self._inner.push_index)

    async def save_to_disk(self, cache_path: Optional[str] = None) -> None:
        """
        Save the session under `<cache_path>/<name>/` for offline reuse.

        A later session with the same name restores it with
        `load_from_disk`. Open that session with `auto_load_on_init=False`
        so the restore downloads no index. A failed or
        interrupted save leaves the last saved snapshot loadable. For a
        built-in model the snapshot records the model id and the exact model
        artifact, so the restored session embeds text with the same model.

        Args:
            cache_path: Directory that holds one snapshot directory per session
                name. A relative path resolves against the current working
                directory, and `~` is not expanded. When omitted, snapshots go
                in `sessions/<project id>/` under the client's `cache_path`, else under the
                `MOSS_SESSION_CACHE_PATH` environment variable, which only session
                snapshots read, else under `moss` in the default cache directory
                (`~/.cache` on macOS and Linux, `%LOCALAPPDATA%` on Windows).
        """
        await asyncio.to_thread(
            self._inner.save_to_disk,
            cache_path,
            client_cache_path=self._client_cache_path,
        )

    async def load_from_disk(
        self, cache_path: Optional[str] = None, *, rebuild_legacy: bool = True
    ) -> int:
        """
        Restore a session saved by `save_to_disk` from `<cache_path>/<name>/`.

        The snapshot replaces this session's documents and model.
        A missing or damaged snapshot raises `MossError` with code
        `DESERIALIZATION` and leaves the session as it was before the call.

        A snapshot saved for a built-in model by an older core has no
        model artifact identity, so the core can only restore it as a
        custom-model session. With `rebuild_legacy` (the default), a session
        opened with the same built-in model rebuilds such a snapshot instead: the
        stored documents are re-embedded with the current model and the upgraded
        snapshot is saved back in the same call, so the rebuild happens once per
        device. It needs the model, so the cloud must be reachable. Custom-model
        sessions and snapshots of another model load without a rebuild. Pass
        `rebuild_legacy=False` to load such a snapshot as a custom-model session.

        Args:
            cache_path: Directory passed to `save_to_disk`, resolved the same way.
                When omitted, the directory `save_to_disk` uses without one.
            rebuild_legacy: Rebuild a built-in model snapshot that has no model
                artifact identity. Defaults to True.

        Returns:
            Number of documents loaded.

        Raises:
            MossError: With code `MODEL_UNAVAILABLE` when a rebuild cannot
                load the model. The snapshot and the session are unchanged,
                so retry later instead of discarding the snapshot.
        """
        return await asyncio.to_thread(
            self._inner.load_from_disk,
            cache_path,
            rebuild_legacy=rebuild_legacy,
            client_cache_path=self._client_cache_path,
        )

    async def close(self) -> None:
        """
        Send the final usage telemetry and free the session's native memory.

        Waits until the telemetry is delivered or 2 seconds pass. Safe to call
        more than once. Afterwards `name` and `model_id` still read and every
        other method raises `InvalidArgumentError`. Leaving a `with` or
        `async with` block calls it.
        """
        await asyncio.to_thread(self._inner.close)

    def __enter__(self) -> "SessionIndex":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self._inner.close()

    async def __aenter__(self) -> "SessionIndex":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    # -- Compatibility warm-up hook --

    async def _get_embedding_service(self) -> None:
        """
        Internal compatibility hook for MossClient.session().

        Built-in model embedding services now live in Rust core; this method
        simply preloads the Rust-owned model so session creation keeps the same
        warm-up behavior.
        """
        if self.model_id != "custom":
            await asyncio.to_thread(self._inner.load_model)

    def _get_custom_embeddings(self, docs: List[DocumentInfo]) -> List[List[float]]:
        missing = [doc.id for doc in docs if not getattr(doc, "embedding", None)]
        if missing:
            raise ValueError(
                f"Documents missing .embedding for custom model: {missing}. "
                "All documents must have .embedding set when using model_id='custom'."
            )
        return [list(doc.embedding) for doc in docs]  # type: ignore[arg-type]
