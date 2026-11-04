"""Pivot jobs API: POST/GET/DELETE /rest/pivot/jobs. Mirrors src/sdk/domains/pivotJobs.ts."""

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import quote

from ..exceptions import PivotJobError
from ..feature_types.pivot_jobs import CreatePivotJobParams, PivotJob, PivotJobResult
from .base import BaseService

PIVOT_JOB_POLL_FAST_MS = 2000
PIVOT_JOB_POLL_SLOW_MS = 5000
PIVOT_JOB_POLL_SLOW_AFTER_MS = 60000


async def _default_sleep(ms: float) -> None:
    await asyncio.sleep(ms / 1000)


def _default_now() -> float:
    return time.monotonic() * 1000


def _job_path(job_id: str) -> str:
    return f"/rest/pivot/jobs/{quote(job_id, safe='')}"


class PivotJobsService(BaseService):
    """Service for asynchronous pivot jobs."""

    async def create_pivot_job(self, params: CreatePivotJobParams) -> PivotJob:
        """POST /rest/pivot/jobs: 202 {job}, or 200 {job: done} on cache hit."""
        res = await self._post("/rest/pivot/jobs", json=dict(params))
        return res["job"]

    async def get_pivot_job(self, job_id: str) -> PivotJob:
        res = await self._get(_job_path(job_id))
        return res["job"]

    async def list_pivot_jobs(self) -> List[PivotJob]:
        res = await self._get("/rest/pivot/jobs")
        return res["jobs"]

    async def get_pivot_job_result(self, job_id: str) -> PivotJobResult:
        return await self._get(f"{_job_path(job_id)}/result")

    async def cancel_pivot_job(self, job_id: str) -> PivotJob:
        res = await self._delete(_job_path(job_id))
        return res["job"]

    async def _cancel_quietly(self, job_id: str) -> None:
        try:
            await self.cancel_pivot_job(job_id)
        except Exception:
            pass

    async def run_pivot_job(
        self,
        params: CreatePivotJobParams,
        on_progress: Optional[Callable[[PivotJob], Any]] = None,
        *,
        sleep: Callable[[float], Awaitable[None]] = _default_sleep,
        now: Callable[[], float] = _default_now,
    ) -> Dict[str, Any]:
        """
        Create the job and poll every 2 s (5 s after 1 min) until it ends.

        done -> {"job", "result"}; failed/canceled -> PivotJobError; task cancelled ->
        best-effort DELETE on the job, then asyncio.CancelledError is re-raised.
        ``sleep`` (ms) and ``now`` (ms) are test hooks.
        """
        started_at = now()
        job: Optional[PivotJob] = None
        try:
            job = await self.create_pivot_job(params)
            if on_progress:
                on_progress(job)
            while job["status"] in ("queued", "running"):
                elapsed = now() - started_at
                await sleep(
                    PIVOT_JOB_POLL_SLOW_MS
                    if elapsed >= PIVOT_JOB_POLL_SLOW_AFTER_MS
                    else PIVOT_JOB_POLL_FAST_MS
                )
                job = await self.get_pivot_job(job["_id"])
                if on_progress:
                    on_progress(job)
        except asyncio.CancelledError:
            if job is not None:
                await self._cancel_quietly(job["_id"])
            raise

        if job["status"] != "done":
            raise PivotJobError(job)
        result = await self.get_pivot_job_result(job["_id"])
        return {"job": job, "result": result}
