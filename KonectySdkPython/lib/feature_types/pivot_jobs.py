"""Pivot job types. Mirror src/sdk/types/pivot.ts of the TypeScript SDK."""

from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

PivotJobStatus = Literal["queued", "running", "done", "failed", "canceled"]
PivotJobStage = Literal["queued", "counting", "reading", "aggregating", "saving"]
PivotJobErrorCode = Literal[
    "interrupted", "too-many-cells", "python-memory", "timeout", "internal"
]


class PivotJobRequest(TypedDict, total=False):
    document: str
    pivotConfig: Dict[str, Any]
    filter: Any
    displayName: str
    displayType: str
    fields: Union[List[str], str]


class CreatePivotJobParams(PivotJobRequest, total=False):
    title: str


class PivotJobErrorInfo(TypedDict):
    code: PivotJobErrorCode
    message: str


class PivotJob(TypedDict, total=False):
    _id: str
    userId: str
    document: str
    title: str
    request: PivotJobRequest
    status: PivotJobStatus
    stage: PivotJobStage
    processed: int
    # None = count timed out: indeterminate progress
    total: Optional[int]
    truncated: bool
    error: PivotJobErrorInfo
    cancelRequested: bool
    podId: str
    heartbeatAt: str
    createdAt: str
    finishedAt: str
    expiresAt: str


# Result blob: server-defined shape plus optional truncated/readCount.
PivotJobResult = Dict[str, Any]
