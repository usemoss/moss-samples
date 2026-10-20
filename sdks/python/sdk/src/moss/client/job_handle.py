from __future__ import annotations

from typing import TYPE_CHECKING

from moss_core import JobStatusResponse

if TYPE_CHECKING:
    from .moss_client import MossClient


class JobHandle:
    """Handle to an in-flight build submitted with `create_index(..., wait=False)`.

    Fire-and-forget: read `job_id`, tear down your process, and later poll
    `client.get_job_status(job_id)` or block on `client.wait_for_job(job_id)`
    from anywhere. In-process, use `status()` for a progress readout or
    `wait()` to block until the build completes.

    Delegates to the client's public async methods — it does not hold any extra
    native resources of its own.
    """

    def __init__(self, client: "MossClient", job_id: str) -> None:
        self._client = client
        self._job_id = job_id

    @property
    def job_id(self) -> str:
        return self._job_id

    async def status(self) -> JobStatusResponse:
        """Current build status: status, progress, current_phase."""
        return await self._client.get_job_status(self._job_id)

    async def wait(self) -> JobStatusResponse:
        """Block until the build completes; raises on failure/timeout."""
        return await self._client.wait_for_job(self._job_id)
