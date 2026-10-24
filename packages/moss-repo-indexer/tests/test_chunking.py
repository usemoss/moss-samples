"""Unit tests for chunkers and build_documents."""

from __future__ import annotations

from pathlib import Path

from moss_repo_indexer import IndexOptions, build_documents
from moss_repo_indexer.chunkers import FileChunkRequest, chunk_code, chunk_markdown


def test_chunk_markdown_headings(tmp_path: Path):
    path = tmp_path / "guide.md"
    content = "# Install\n\nRun npm.\n\n## Setup\n\nSet env.\n"
    docs = chunk_markdown(
        FileChunkRequest(
            path=path,
            root=tmp_path,
            content=content,
            language="markdown",
        )
    )
    types = {d.metadata["type"] for d in docs}
    assert "page" in types
    assert "header" in types
    assert "text" in types
    assert docs[0].id == "guide.md"


def test_chunk_code_symbol(tmp_path: Path):
    path = tmp_path / "auth.py"
    content = "class AuthMiddleware:\n    def process(self):\n        return True\n" + (
        "    # pad\n" * 80
    )
    docs = chunk_code(
        FileChunkRequest(
            path=path,
            root=tmp_path,
            content=content,
            language="python",
        )
    )
    assert docs
    assert docs[0].metadata["type"] == "code"
    assert docs[0].metadata["symbol"] == "AuthMiddleware"
    assert "auth.py :: AuthMiddleware" in docs[0].text


def test_build_documents(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    return 0\n")
    (tmp_path / "README.md").write_text("# Demo\n\nHello.\n")

    docs = build_documents(tmp_path, IndexOptions(repo_name="demo-repo"))
    assert len(docs) >= 2
    assert all(d.metadata.get("repo") == "demo-repo" for d in docs)
    assert all("navigation" in d.metadata for d in docs)
