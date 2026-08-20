"""Tests for the update payload built by KonectyClient (PUT /rest/data/:module)."""

from datetime import datetime, timezone

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.types import KonectyUpdateId

FAKE_AUTH_ID = "fake-auth-id-not-a-real-token"
RECORD_ID = "act-1"
UPDATED_AT = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

UPDATE_OK = {"success": True, "data": [{"_id": RECORD_ID, "status": "Concluída"}]}

# A payload carrying every field the client is expected to strip, plus the two it must keep.
PAYLOAD = {
    "status": "Concluída",
    "_updatedBy": {"_id": "broker-1"},
    "_id": "should-be-stripped",
    "code": 123,
    "_updatedAt": "2026-08-19T11:00:00.000Z",
    "_createdAt": "2026-08-01T11:00:00.000Z",
    "_createdBy": {"_id": "someone"},
}


def _client(stub_server) -> KonectyClient:
    return KonectyClient(base_url=stub_server.base_url, token=FAKE_AUTH_ID)


@pytest.mark.asyncio
async def test_update_sends_updated_by_and_strips_the_other_system_fields(stub_server):
    stub_server.route("PUT", "/rest/data/Activity", UPDATE_OK)

    await _client(stub_server).update(
        "Activity",
        [KonectyUpdateId.from_dict({"_id": RECORD_ID, "_updatedAt": UPDATED_AT})],
        dict(PAYLOAD),
    )

    sent = stub_server.requests[0]["json"]
    assert sent["data"] == {"status": "Concluída", "_updatedBy": {"_id": "broker-1"}}
    assert sent["ids"][0]["_id"] == RECORD_ID


@pytest.mark.asyncio
async def test_update_one_sends_updated_by_and_strips_the_other_system_fields(
    stub_server,
):
    stub_server.route("PUT", "/rest/data/Activity", UPDATE_OK)

    await _client(stub_server).update_one(
        "Activity", RECORD_ID, UPDATED_AT, dict(PAYLOAD)
    )

    sent = stub_server.requests[0]["json"]
    assert sent["data"] == {"status": "Concluída", "_updatedBy": {"_id": "broker-1"}}
    assert sent["ids"][0]["_id"] == RECORD_ID


@pytest.mark.asyncio
async def test_create_still_strips_updated_by(stub_server):
    stub_server.route("POST", "/rest/data/Activity", UPDATE_OK)

    await _client(stub_server).create("Activity", dict(PAYLOAD))

    sent = stub_server.requests[0]["json"]
    assert "_updatedBy" not in sent
    assert sent["status"] == "Concluída"
