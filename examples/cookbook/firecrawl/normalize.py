"""
Web crawl markdown normalization: chrome strip + page-specific title extraction.

Strips repeated boilerplate (navigation, headers, footers, sidebars) from
crawled markdown and extracts page-specific titles for indexing quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class NormalizationMetrics:
    """Metrics for chrome stripping normalization."""
    original_length: int
    normalized_length: int
    chrome_ratio: float  # 0.0 = no chrome removed, 1.0 = entirely chrome
    title_source: str  # "h1", "metadata", "url_fallback"
    stripped_patterns: list[str] = field(default_factory=list)


@dataclass
class NormalizedPage:
    """Result of normalizing a crawled page."""
    url: str
    markdown: str
    title: str
    metrics: NormalizationMetrics


# Common chrome patterns (order matters - most specific first)
CHROME_PATTERNS: list[re.Pattern[str]] = [
    # Skip to main content links
    re.compile(r'\[Skip to main content\]\([^)]*\)\s*\n*', re.IGNORECASE),
    # Navigation breadcrumbs (e.g., "Docs > API > Reference")
    re.compile(r'^\[?[A-Z][a-z]+ Docs?\s*(?:home page)?\s*\]?\s*\n*', re.MULTILINE),
    # Logo/image links at top (common in docs sites)
    re.compile(r'!\[[^\]]*\]\([^)]*(?:logo|icon)[^)]*\)\s*\n*', re.IGNORECASE),
    # Sidebar navigation markers
    re.compile(r'\[?(?:Sidebar|Navigation|Menu)\s*(?:Menu)?\]?\s*\n*', re.IGNORECASE),
    # Footer markers
    re.compile(r'\n---\s*\n.*?(?:©|Copyright|Built with|Powered by).*$', re.DOTALL | re.IGNORECASE),
    # Cookie consent notices
    re.compile(r'(?:Cookie|Privacy)\s*(?:Policy|Notice|Consent)[^.]*\.?\s*\n*', re.IGNORECASE),
    # Edit this page links
    re.compile(r'\[Edit this page\]\([^)]*\)\s*\n*', re.IGNORECASE),
    # Table of contents headers (when repeated)
    re.compile(r'^##\s*Table of Contents\s*\n', re.MULTILINE),
]

# Title extraction patterns (for markdown)
TITLE_PATTERNS: list[re.Pattern[str]] = [
    # First H1 heading
    re.compile(r'^#\s+(.+)$', re.MULTILINE),
    # Frontmatter title (already extracted separately)
]


def extract_page_title(markdown: str, metadata: dict | None = None, url: str = "") -> tuple[str, str]:
    """
    Extract page-specific title from markdown content or metadata.

    Returns (title, source) where source is one of: "h1", "metadata", "url_fallback".
    """
    # 1. Try to get title from metadata (most reliable for crawled pages)
    if metadata:
        for key in ("title", "og_title"):
            title = metadata.get(key)
            if title and not _is_site_generic_title(title):
                return title.strip(), "metadata"

    # 2. Try first H1 in markdown
    match = TITLE_PATTERNS[0].search(markdown)
    if match:
        title = match.group(1).strip()
        if not _is_site_generic_title(title):
            return title, "h1"

    # 3. Fallback: extract from URL path
    if url:
        path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/").split("/")[-1]
        if path and path not in ("index", "home", ""):
            # Convert slug to title
            title = path.replace("-", " ").replace("_", " ").title()
            return title, "url_fallback"

    return "", "url_fallback"


def _is_site_generic_title(title: str) -> bool:
    """Check if title is site-wide generic (should not be used as page title)."""
    generic_patterns = [
        r"docs?\s+home",
        r"^home$",
        r"^welcome$",
        r"^documentation$",
        r"^api\s+reference$",  # too generic for specific pages
        r"^index$",
    ]
    title_lower = title.lower().strip()
    return any(re.search(p, title_lower) for p in generic_patterns)


def strip_chrome(markdown: str, extra_patterns: list[re.Pattern[str]] | None = None) -> tuple[str, list[str]]:
    """
    Strip common chrome/boilerplate from crawled markdown.

    Returns (cleaned_markdown, list_of_stripped_pattern_names).
    """
    cleaned = markdown
    stripped = []

    patterns = CHROME_PATTERNS + (extra_patterns or [])

    for i, pattern in enumerate(patterns):
        original_len = len(cleaned)
        cleaned = pattern.sub("", cleaned)
        if len(cleaned) < original_len:
            stripped.append(f"pattern_{i}")

    # Clean up excessive whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()

    return cleaned, stripped


def normalize_crawled_markdown(
    url: str,
    markdown: str,
    metadata: dict | None = None,
    extra_patterns: list[re.Pattern[str]] | None = None,
) -> NormalizedPage:
    """
    Normalize crawled markdown: strip chrome and extract page-specific title.

    Args:
        url: Source URL of the page
        markdown: Raw crawled markdown content
        metadata: Optional metadata dict with title, og_title, etc.
        extra_patterns: Optional additional regex patterns to strip

    Returns:
        NormalizedPage with cleaned markdown, title, and metrics
    """
    original_length = len(markdown)

    # Extract title first (before stripping, as H1 might be chrome)
    title, title_source = extract_page_title(markdown, metadata, url)

    # Strip chrome
    normalized_markdown, stripped_patterns = strip_chrome(markdown, extra_patterns)
    normalized_length = len(normalized_markdown)

    # Calculate chrome ratio
    chrome_ratio = 1.0 - (normalized_length / original_length) if original_length > 0 else 0.0

    return NormalizedPage(
        url=url,
        markdown=normalized_markdown,
        title=title,
        metrics=NormalizationMetrics(
            original_length=original_length,
            normalized_length=normalized_length,
            chrome_ratio=chrome_ratio,
            title_source=title_source,
            stripped_patterns=stripped_patterns,
        ),
    )
