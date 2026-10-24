"""Ensure moss is importable for unit tests (stub when SDK is not installed)."""

from __future__ import annotations

import sys
import types


def _install_moss_stub() -> None:
    moss = types.ModuleType("moss")

    class DocumentInfo:
        def __init__(self, id, text, metadata=None, embedding=None):
            self.id = id
            self.text = text
            self.metadata = metadata
            self.embedding = embedding

    class MutationResult:
        def __init__(self, job_id="job", doc_count=0):
            self.job_id = job_id
            self.doc_count = doc_count

    class MutationOptions:
        def __init__(self, upsert=False):
            self.upsert = upsert

    class MossClient:
        def __init__(self, project_id, project_key):
            self.project_id = project_id
            self.project_key = project_key

        async def delete_index(self, name):
            raise Exception("not found")

        async def create_index(self, name, docs, model_id=None):
            return MutationResult(doc_count=len(docs))

        async def add_docs(self, name, docs, options=None):
            return MutationResult(doc_count=len(docs))

    moss.DocumentInfo = DocumentInfo
    moss.MutationResult = MutationResult
    moss.MutationOptions = MutationOptions
    moss.MossClient = MossClient
    sys.modules["moss"] = moss


try:
    import moss  # noqa: F401
except ImportError:
    _install_moss_stub()
