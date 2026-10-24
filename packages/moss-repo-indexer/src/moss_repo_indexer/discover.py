"""Walk a repository root and yield files to index."""

from __future__ import annotations

import fnmatch
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path

from .types import IndexOptions


def discover_files(root: Path, options: IndexOptions) -> list[Path]:
    """Return absolute paths of files that should be chunked."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Repository root is not a directory: {root}")

    candidates = _list_candidates(root, options)
    matched = [
        path
        for path in candidates
        if _is_under_root(path, root) and _matches_include(path, root, options.include_globs)
    ]
    sized = [path for path in matched if _within_size_limit(path, options.max_file_bytes)]
    return sorted(sized)


def _list_candidates(root: Path, options: IndexOptions) -> list[Path]:
    if options.respect_gitignore and _is_git_work_tree(root):
        tracked = _git_list_files(root)
        if tracked is not None:
            return tracked
    return _walk_filesystem(root, set(options.exclude_dirs))


def _is_git_work_tree(root: Path) -> bool:
    if not (root / ".git").exists():
        return False
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_list_files(root: Path) -> list[Path] | None:
    """List tracked and untracked non-ignored files under root.

    Uses --cached --others --exclude-standard so the candidate set matches a
    normal working tree (not only committed files). Returns None to fall back
    to a filesystem walk when git is unavailable or fails.
    """
    if subprocess.run(["git", "--version"], capture_output=True, check=False).returncode != 0:
        return None
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    rel_paths = [p for p in result.stdout.decode("utf-8", errors="replace").split("\0") if p]
    files: list[Path] = []
    for rel in rel_paths:
        path = root / rel
        if _is_indexable_file(path, root):
            files.append(path)
    return files


def _walk_filesystem(root: Path, exclude_dirs: set[str]) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in exclude_dirs and not (current / name).is_symlink()
        ]
        for name in filenames:
            path = current / name
            if _is_indexable_file(path, root):
                files.append(path)
    return files


def _is_indexable_file(path: Path, root: Path) -> bool:
    if path.is_symlink():
        return path.exists() and _is_under_root(path, root)
    if not path.is_file():
        return False
    return _is_under_root(path, root)


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _matches_include(path: Path, root: Path, include_globs: Iterable[str]) -> bool:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    name = path.name
    for pattern in include_globs:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(name, pattern[3:]):
            return True
    return False


def _within_size_limit(path: Path, max_file_bytes: int) -> bool:
    try:
        return path.stat().st_size <= max_file_bytes
    except OSError:
        return False
