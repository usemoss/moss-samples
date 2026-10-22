"""Tests for web crawl markdown normalization against actual crawled output."""

from normalize import normalize_crawled_markdown, extract_page_title, strip_chrome


# Actual crawled output from docs.moss.dev (from notebook output)
SAMPLE_CRAWLED_OUTPUT = """[Skip to main content](https://docs.moss.dev/docs/start/what-is-moss#content-area)

[Moss Docs home page![light logo](https://mintcdn.com/moss-afcfb0b6/b460p8xEydp14WML/logo/moss-wordmark-light.svg?fit=max&fm=svg&ixlib=markdown-3.2.0&w=1000)
](/)

# What is Moss

Moss is a real-time semantic search runtime for AI agents targeting sub-10ms query latency.

## Key Features

- On-device inference using bundled embedding models
- No external API calls needed for queries
- Sub-10ms query latency

## Getting Started

To get started with Moss, install the SDK:

```python
pip install moss
```

Then create your first index:

```python
from moss import MossClient

client = MossClient(project_id, project_key)
await client.create_index("my-index", documents)
```"""

SAMPLE_CRAWLED_OUTPUT_TITLE = """[Skip to main content](https://docs.moss.dev/docs/api-reference/v1/getting-started/introduction#content-area)

[Moss Docs home page![light logo](https://mintcdn.com/moss-afcfb0b6/b460p8xEydp14WML/logo/moss-wordmark-light.svg?fit=max&fm=svg&ixlib=markdown-3.2.0&w=1000)
](/)

# Getting Started with the Moss API

This guide walks you through your first API call."""

SAMPLE_METADATA = {"title": "What is Moss - Documentation", "og_title": "What is Moss"}

SITE_GENERIC_TITLE = {"title": "Moss Docs home page"}


def test_strip_skip_to_main_content():
    """Verify skip-to-main-content links are stripped."""
    cleaned, stripped = strip_chrome(SAMPLE_CRAWLED_OUTPUT)
    assert "[Skip to main content]" not in cleaned
    assert len(stripped) > 0


def test_strip_logo_link():
    """Verify logo/image links at top are stripped."""
    cleaned, stripped = strip_chrome(SAMPLE_CRAWLED_OUTPUT)
    assert "[Moss Docs home page![light logo]" not in cleaned
    assert "![" not in cleaned.split("# What is Moss")[0]  # Before first H1


def test_preserves_content():
    """Verify actual page content is preserved."""
    cleaned, _ = strip_chrome(SAMPLE_CRAWLED_OUTPUT)
    assert "# What is Moss" in cleaned
    assert "Key Features" in cleaned
    assert "pip install moss" in cleaned


def test_extract_title_from_metadata():
    """Verify title extraction prefers metadata when not generic."""
    title, source = extract_page_title(SAMPLE_CRAWLED_OUTPUT, SAMPLE_METADATA)
    assert title == "What is Moss - Documentation"
    assert source == "metadata"


def test_fallback_to_h1_when_metadata_generic():
    """Verify fallback to H1 when metadata title is site-generic."""
    title, source = extract_page_title(SAMPLE_CRAWLED_OUTPUT, SITE_GENERIC_TITLE)
    assert title == "What is Moss"
    assert source == "h1"


def test_extract_title_from_h1():
    """Verify title extraction from first H1."""
    title, source = extract_page_title(SAMPLE_CRAWLED_OUTPUT_TITLE, None)
    assert title == "Getting Started with the Moss API"
    assert source == "h1"


def test_chrome_ratio_calculation():
    """Verify chrome ratio metric is calculated correctly."""
    result = normalize_crawled_markdown(
        url="https://docs.moss.dev/docs/start/what-is-moss",
        markdown=SAMPLE_CRAWLED_OUTPUT,
        metadata=SAMPLE_METADATA,
    )
    assert result.metrics.chrome_ratio > 0  # Some chrome was stripped
    assert result.metrics.chrome_ratio < 1.0  # Not all content was chrome
    assert result.metrics.normalized_length < result.metrics.original_length


def test_full_normalization():
    """Verify end-to-end normalization produces clean output."""
    result = normalize_crawled_markdown(
        url="https://docs.moss.dev/docs/start/what-is-moss",
        markdown=SAMPLE_CRAWLED_OUTPUT,
        metadata=SAMPLE_METADATA,
    )
    # Title should be page-specific, not site-generic
    assert result.title == "What is Moss - Documentation"
    # Content should have chrome stripped
    assert "[Skip to main content]" not in result.markdown
    assert "# What is Moss" in result.markdown
    # Metrics should be populated
    assert result.metrics.original_length > 0
    assert result.metrics.normalized_length > 0


def test_url_fallback_title():
    """Verify title fallback to URL path when no metadata or H1."""
    title, source = extract_page_title("No title here", None, "https://docs.moss.dev/docs/start/what-is-moss")
    assert title == "What Is Moss"
    assert source == "url_fallback"


if __name__ == "__main__":
    test_strip_skip_to_main_content()
    test_strip_logo_link()
    test_preserves_content()
    test_extract_title_from_metadata()
    test_fallback_to_h1_when_metadata_generic()
    test_extract_title_from_h1()
    test_chrome_ratio_calculation()
    test_full_normalization()
    test_url_fallback_title()
    print("All tests passed!")
