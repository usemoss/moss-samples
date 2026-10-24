"""Shared credentials, options, and document metadata contract.

Metadata keys are string-valued so both the Python and TypeScript packages
emit the same JSON shape for Moss DocumentInfo.metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Document metadata contract (mirrored by the TS package) ---

METADATA_PATH = "path"
METADATA_LANGUAGE = "language"
METADATA_TYPE = "type"
METADATA_START_LINE = "start_line"
METADATA_END_LINE = "end_line"
METADATA_SYMBOL = "symbol"
METADATA_REPO = "repo"
METADATA_REF = "ref"
METADATA_TITLE = "title"
METADATA_NAVIGATION = "navigation"

CHUNK_TYPE_CODE = "code"
CHUNK_TYPE_MARKDOWN = "markdown"
CHUNK_TYPE_HEADER = "header"
CHUNK_TYPE_TEXT = "text"
CHUNK_TYPE_PAGE = "page"

DEFAULT_MODEL_NAME = "moss-minilm"
DEFAULT_INCLUDE_GLOBS: list[str] = [
    "**/*.py",
    "**/*.ts",
    "**/*.tsx",
    "**/*.js",
    "**/*.jsx",
    "**/*.go",
    "**/*.rs",
    "**/*.java",
    "**/*.md",
    "**/*.mdx",
]
DEFAULT_EXCLUDE_DIRS: list[str] = [
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
]


@dataclass
class MossCreds:
    project_id: str
    project_key: str
    index_name: str
    model_name: str = DEFAULT_MODEL_NAME


@dataclass
class IndexOptions:
    """Options for discovering and chunking a repository."""

    include_globs: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE_GLOBS))
    exclude_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_DIRS))
    respect_gitignore: bool = True
    ref: str | None = None
    max_file_bytes: int = 1_000_000
    repo_name: str | None = None


@dataclass
class SyncOptions:
    """End-to-end index options. dry_run skips upload."""

    source: str
    creds: MossCreds
    index: IndexOptions = field(default_factory=IndexOptions)
    dry_run: bool = False
    upsert: bool = False
    replace: bool = False


def metadata_contract() -> dict[str, str]:
    """Return the canonical metadata key → description mapping."""
    return {
        METADATA_PATH: "Repository-relative file path",
        METADATA_LANGUAGE: "Language id (python, typescript, markdown, ...)",
        METADATA_TYPE: "Chunk kind: code | markdown | header | text | page",
        METADATA_START_LINE: "1-based start line (string)",
        METADATA_END_LINE: "1-based end line (string)",
        METADATA_SYMBOL: "Optional symbol or heading name",
        METADATA_REPO: "Optional repository name or URL",
        METADATA_REF: "Optional git ref / branch",
        METADATA_TITLE: "Display title (symbol, heading, or basename)",
        METADATA_NAVIGATION: "Editor/UI target, e.g. path:startLine",
    }
