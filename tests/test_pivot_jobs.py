"""
Pivot jobs (POST/GET/DELETE /rest/pivot/jobs).

Paridade com o SDK TypeScript: `src/__test__/api/pivotJobs.test.ts` (repo konecty/konecty-sdk)
usa a MESMA entrada (PARAMS), as MESMAS respostas e espera a MESMA URL, método e corpo.
C1..C12 abaixo têm o mesmo número dos casos de lá.

Desvio conhecido: o erro HTTP (C6) segue o padrão deste SDK (`KonectyAPIError` com a lista
`errors` do corpo, como `get_pivot`), e não a mensagem "<status> - <statusText>" do TS.
"""

import asyncio
from typing import Any, Dict, List

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import KonectyAPIError, PivotJobError

PARAMS = {
    "document": "Opportunity",
    "title": "Funil",
    "pivotConfig": {
        "rows": [{"field": "status"}],
        "values": [{"field": "_id", "aggregator": "count"}],
    },
    "filter": {"match": "and", "conditions": []},
    "fields": "status,_id",
}


def job(**over: Any) -> Dict[str, Any]:
    base = {
        "_id": "abc",
        "userId": "u1",
        "document": "Opportunity",
        "title": "Funil",
        "request": PARAMS,
        "status": "queued",
        "stage": "queued",
        "processed": 0,
        "total": None,
        "truncated": False,
        "cancelRequested": False,
        "createdAt": "2026-11-04T00:00:00.000Z",
    }
    base.update(over)
    return base


class _Sequence(dict):
    """Responses registered as a list answer one per request; the last one repeats."""

    def get(self, key, default=None):
        value = super().get(key)
        if value is None:
            return default
        body, status = value
        if isinstance(body, list):
            current = body.pop(0) if len(body) > 1 else body[0]
            return (current, status)
        return value


@pytest.fixture
def server(stub_server):
    stub_server._responses = _Sequence()
    return stub_server


def client_for(server) -> KonectyClient:
    return KonectyClient(base_url=server.base_url, token="fake-key")


def seen(server) -> List[str]:
    return [f"{r['method']} {r['path']}" for r in server.requests]


@pytest.mark.asyncio
async def test_c1_create_posts_params_as_json_body(server) -> None:
    server.route("POST", "/rest/pivot/jobs", {"success": True, "job": job()}, 202)
    result = await client_for(server).create_pivot_job(PARAMS)
    assert result["_id"] == "abc"
    assert len(server.requests) == 1
    req = server.requests[0]
    assert req["method"] == "POST"
    assert req["raw_path"] == "/rest/pivot/jobs"
    assert req["json"] == PARAMS
    assert req["authorization"] == "fake-key"


@pytest.mark.asyncio
async def test_c2_get_encodes_the_id(server) -> None:
    server.route(
        "GET", "/rest/pivot/jobs/job 1/x", {"success": True, "job": job(_id="job 1/x")}
    )
    result = await client_for(server).get_pivot_job("job 1/x")
    assert result["_id"] == "job 1/x"
    assert server.requests[0]["method"] == "GET"
    assert server.requests[0]["raw_path"] == "/rest/pivot/jobs/job%201%2Fx"


@pytest.mark.asyncio
async def test_c3_list_returns_jobs_array(server) -> None:
    server.route(
        "GET", "/rest/pivot/jobs", {"success": True, "jobs": [job(), job(_id="b")]}
    )
    result = await client_for(server).list_pivot_jobs()
    assert [j["_id"] for j in result] == ["abc", "b"]
    assert server.requests[0]["method"] == "GET"
    assert server.requests[0]["raw_path"] == "/rest/pivot/jobs"
    assert server.requests[0]["json"] is None


@pytest.mark.asyncio
async def test_c4_result_returns_raw_blob(server) -> None:
    server.route(
        "GET",
        "/rest/pivot/jobs/abc/result",
        {"success": True, "rows": [], "truncated": True, "readCount": 7},
    )
    result = await client_for(server).get_pivot_job_result("abc")
    assert result["truncated"] is True
    assert result["readCount"] == 7
    assert server.requests[0]["method"] == "GET"
    assert server.requests[0]["raw_path"] == "/rest/pivot/jobs/abc/result"


@pytest.mark.asyncio
async def test_c5_cancel_sends_delete_without_body(server) -> None:
    server.route(
        "DELETE", "/rest/pivot/jobs/abc", {"success": True, "job": job(cancelRequested=True)}
    )
    result = await client_for(server).cancel_pivot_job("abc")
    assert result["cancelRequested"] is True
    assert server.requests[0]["method"] == "DELETE"
    assert server.requests[0]["raw_path"] == "/rest/pivot/jobs/abc"
    assert server.requests[0]["json"] is None


@pytest.mark.asyncio
async def test_c6_raises_on_4xx(server) -> None:
    server.route("GET", "/rest/pivot/jobs/nope", {"success": False}, 404)
    with pytest.raises(KonectyAPIError):
        await client_for(server).get_pivot_job("nope")


def serve(server, states: List[Dict[str, Any]]) -> None:
    server.route("POST", "/rest/pivot/jobs", {"success": True, "job": states[0]}, 202)
    server.route(
        "GET",
        "/rest/pivot/jobs/abc",
        [{"success": True, "job": s} for s in states[1:]] or [{"success": True, "job": states[0]}],
    )
    server.route(
        "GET",
        "/rest/pivot/jobs/abc/result",
        {"success": True, "rows": [1], "truncated": False, "readCount": 1},
    )
    server.route(
        "DELETE", "/rest/pivot/jobs/abc", {"success": True, "job": job(cancelRequested=True)}
    )


@pytest.mark.asyncio
async def test_c7_polls_every_2s_until_done_then_fetches_result_once(server) -> None:
    serve(
        server,
        [
            job(),
            job(status="running", stage="reading", processed=5, total=10),
            job(status="done", stage="saving", processed=10, total=10),
        ],
    )
    sleeps: List[float] = []
    progress: List[str] = []

    async def sleep(ms: float) -> None:
        sleeps.append(ms)

    out = await client_for(server).run_pivot_job(
        PARAMS, lambda j: progress.append(j["status"]), sleep=sleep
    )
    assert sleeps == [2000, 2000]
    assert progress == ["queued", "running", "done"]
    assert out["job"]["status"] == "done"
    assert out["result"]["readCount"] == 1
    assert seen(server) == [
        "POST /rest/pivot/jobs",
        "GET /rest/pivot/jobs/abc",
        "GET /rest/pivot/jobs/abc",
        "GET /rest/pivot/jobs/abc/result",
    ]


@pytest.mark.asyncio
async def test_c8_switches_to_5s_after_one_minute(server) -> None:
    serve(
        server,
        [job(), job(status="running"), job(status="running"), job(status="done")],
    )
    clock = [0.0]
    sleeps: List[float] = []

    async def sleep(ms: float) -> None:
        sleeps.append(ms)
        clock[0] += 60000 if ms == 2000 else ms

    await client_for(server).run_pivot_job(PARAMS, now=lambda: clock[0], sleep=sleep)
    assert sleeps == [2000, 5000, 5000]


async def _no_sleep(ms: float) -> None:
    return None


@pytest.mark.asyncio
async def test_c9_failed_raises_pivot_job_error_with_code_and_job(server) -> None:
    serve(
        server,
        [
            job(),
            job(status="failed", error={"code": "too-many-cells", "message": "muitas células"}),
        ],
    )
    with pytest.raises(PivotJobError) as info:
        await client_for(server).run_pivot_job(PARAMS, sleep=_no_sleep)
    assert info.value.code == "too-many-cells"
    assert str(info.value) == "muitas células"
    assert info.value.job["status"] == "failed"
    assert not any(r["path"].endswith("/result") for r in server.requests)


@pytest.mark.asyncio
async def test_c10_canceled_raises_with_code_canceled(server) -> None:
    serve(server, [job(), job(status="canceled")])
    with pytest.raises(PivotJobError) as info:
        await client_for(server).run_pivot_job(PARAMS, sleep=_no_sleep)
    assert info.value.code == "canceled"


@pytest.mark.asyncio
async def test_c11_cancellation_sends_delete_and_reraises(server) -> None:
    serve(server, [job(), job(status="running"), job(status="running")])
    holder: Dict[str, asyncio.Task] = {}

    async def sleep(ms: float) -> None:
        holder["task"].cancel()
        await asyncio.sleep(0)

    holder["task"] = asyncio.ensure_future(
        client_for(server).run_pivot_job(PARAMS, sleep=sleep)
    )
    with pytest.raises(asyncio.CancelledError):
        await holder["task"]
    assert seen(server) == ["POST /rest/pivot/jobs", "DELETE /rest/pivot/jobs/abc"]


@pytest.mark.asyncio
async def test_c12_does_not_poll_when_create_already_answers_done(server) -> None:
    serve(server, [job(status="done")])
    sleeps: List[float] = []

    async def sleep(ms: float) -> None:
        sleeps.append(ms)

    out = await client_for(server).run_pivot_job(PARAMS, sleep=sleep)
    assert out["job"]["status"] == "done"
    assert sleeps == []
    assert seen(server) == ["POST /rest/pivot/jobs", "GET /rest/pivot/jobs/abc/result"]
