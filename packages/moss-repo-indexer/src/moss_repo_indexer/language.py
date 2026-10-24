"""Map file extensions to language ids used in metadata."""

from __future__ import annotations

from pathlib import Path

_EXTENSION_LANGUAGE = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".md": "markdown",
    ".mdx": "markdown",
}

_MARKDOWN_EXTENSIONS = {".md", ".mdx"}


def language_for_path(path: Path) -> str:
    return _EXTENSION_LANGUAGE.get(path.suffix.lower(), "text")


def is_markdown_path(path: Path) -> bool:
    return path.suffix.lower() in _MARKDOWN_EXTENSIONS
