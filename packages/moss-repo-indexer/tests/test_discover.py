"""Unit tests for resolve_source and discover_files."""

from __future__ import annotations

from pathlib import Path

import pytest

from moss_repo_indexer import IndexOptions, build_documents, discover_files, resolve_source
from moss_repo_indexer.clone import _is_git_url, _repo_name_from_url


def test_resolve_local_path(tmp_path: Path):
    resolved = resolve_source(str(tmp_path))
    assert resolved.root == tmp_path.resolve()
    assert resolved.cleanup is False
    assert resolved.repo_name == tmp_path.name


def test_resolve_missing_path():
    with pytest.raises(FileNotFoundError):
        resolve_source("/tmp/moss-repo-indexer-missing-xyz")


def test_git_url_helpers():
    assert _is_git_url("https://github.com/org/repo.git")
    assert _is_git_url("git@github.com:org/repo.git")
    assert not _is_git_url("/local/path")
    assert _repo_name_from_url("https://github.com/org/cool-repo.git") == "cool-repo"
    assert _repo_name_from_url("git@github.com:org/cool-repo.git") == "cool-repo"


def test_discover_filters(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print(1)\n")
    (tmp_path / "README.md").write_text("# hi\n")
    (tmp_path / "notes.txt").write_text("skip\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("export default 1\n")
    huge = tmp_path / "src" / "huge.py"
    huge.write_bytes(b"x" * 1_000_001)

    files = discover_files(tmp_path, IndexOptions())
    rels = sorted(p.relative_to(tmp_path.resolve()).as_posix() for p in files)
    assert rels == ["README.md", "src/app.py"]


def test_discover_skips_symlink_escape(tmp_path: Path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    secret = outside / "secret.py"
    secret.write_text("SECRET = 1\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print(1)\n")
    link = tmp_path / "leak.py"
    link.symlink_to(secret)

    files = discover_files(tmp_path, IndexOptions())
    rels = [p.relative_to(tmp_path.resolve()).as_posix() for p in files]
    assert "leak.py" not in rels
    assert "src/app.py" in rels


def test_build_documents_accepts_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return 0\n")
    monkeypatch.chdir(tmp_path)
    docs = build_documents(Path("./src"), IndexOptions(repo_name="demo"))
    assert docs
    assert all(d.metadata and d.metadata.get("path", "").startswith("app.py") for d in docs)
