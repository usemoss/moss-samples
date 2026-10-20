from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, List, Literal, Mapping, Optional

WebSourceStatus = Literal["idle", "crawling", "failed", "removing"]
RefreshCadence = Literal["daily", "weekly", "manual"]
CreateRefreshCadence = Literal["daily", "weekly"]


@dataclass(frozen=True)
class WebSource:
    """Public web-source record returned by manage actions."""

    id: str
    index_name: str
    root_url: str
    max_pages: int
    max_documents: int
    max_depth: int
    respect_robots: bool
    parse_documents: bool
    refresh_cadence: RefreshCadence
    next_refresh_at: Optional[str]
    last_crawled_at: Optional[str]
    last_page_count: Optional[int]
    last_doc_count: Optional[int]
    status: WebSourceStatus
    last_error_code: Optional[str]
    include_paths: Optional[List[str]] = None
    exclude_paths: Optional[List[str]] = None
    created_at: Optional[str] = None


@dataclass(frozen=True)
class CreateWebSourceResult(WebSource):
    """Create response: public web-source record plus required `job_id`.

    Poll `job_id` with `get_job_status`.
    """

    job_id: str = field(kw_only=True)


@dataclass(frozen=True)
class UpdateWebSourceResult(WebSource):
    """Update response: public web-source record plus optional `job_id`.

    `job_id` is present when `resync` is true and the server enqueued a
    crawl. Poll with `get_job_status`.
    """

    job_id: Optional[str] = field(default=None, kw_only=True)


@dataclass(frozen=True)
class ResyncWebSourceResult:
    """Resync response with required `job_id` for `get_job_status`."""

    id: str
    job_id: str
    status: Optional[str] = None
    index_name: Optional[str] = None


@dataclass(frozen=True)
class DeleteWebSourceResult:
    """Delete response.

    `purge_job_id` is present when a purge was enqueued. Poll with
    `get_job_status`. Does not delete the index.
    """

    deleted: bool
    id: str
    purge_job_id: Optional[str] = None


def web_source_from_public(data: Mapping[str, Any]) -> WebSource:
    return WebSource(
        id=str(data["id"]),
        index_name=str(data["indexName"]),
        root_url=str(data["rootUrl"]),
        max_pages=int(data["maxPages"]),
        max_documents=int(data["maxDocuments"]),
        max_depth=int(data["maxDepth"]),
        respect_robots=bool(data["respectRobots"]),
        parse_documents=bool(data["parseDocuments"]),
        refresh_cadence=data["refreshCadence"],
        next_refresh_at=data.get("nextRefreshAt"),
        last_crawled_at=data.get("lastCrawledAt"),
        last_page_count=data.get("lastPageCount"),
        last_doc_count=data.get("lastDocCount"),
        status=data["status"],
        last_error_code=data.get("lastErrorCode"),
        include_paths=data.get("includePaths"),
        exclude_paths=data.get("excludePaths"),
        created_at=data.get("createdAt"),
    )


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def create_web_source_from_public(
    data: Mapping[str, Any],
) -> CreateWebSourceResult:
    source = web_source_from_public(data)
    return CreateWebSourceResult(**asdict(source), job_id=str(data["jobId"]))


def update_web_source_from_public(
    data: Mapping[str, Any],
) -> UpdateWebSourceResult:
    source = web_source_from_public(data)
    return UpdateWebSourceResult(
        **asdict(source),
        job_id=_optional_str(data.get("jobId")),
    )


def delete_web_source_from_public(
    data: Mapping[str, Any],
    source_id: str,
) -> DeleteWebSourceResult:
    return DeleteWebSourceResult(
        deleted=bool(data["deleted"]),
        id=str(data.get("id", source_id)),
        purge_job_id=_optional_str(data.get("purgeJobId")),
    )
