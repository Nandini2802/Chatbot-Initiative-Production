"""
CHAT_REQUEST_RECEIVED logs the feature keys the app sent (key_features),
so access denials can be traced to what actually arrived.
Uses the real audit logger to prove the field survives its allowlist.
"""
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import chat
from app.core.dependencies import get_session_service


def test_logged_key_features_helper():
    assert chat.logged_key_features(None) == ("<not sent>", 0)
    assert chat.logged_key_features("") == ("<empty>", 0)
    assert chat.logged_key_features(" , ,") == ("<empty>", 0)
    assert chat.logged_key_features("UDPage, DAR Dashboard ,HowToVideos") == (
        "dardashboard,howtovideos,udpage", 3)


def _client(monkeypatch):
    async def fake_stream(**kwargs):
        yield "data: ok\n\n"

    monkeypatch.setattr(chat, "stream_chat_response", Mock(side_effect=fake_stream))

    session_service = SimpleNamespace(
        create_session=AsyncMock(return_value=SimpleNamespace(id="s1")),
        admit_chat_message=AsyncMock(),
    )
    app = FastAPI()
    app.state.clients = object()
    app.state.walkthrough_engine = object()
    app.dependency_overrides[get_session_service] = lambda: session_service

    @app.middleware("http")
    async def corr(request, call_next):
        request.state.correlation_id = "corr-1"
        return await call_next(request)

    app.include_router(chat.router, prefix="/api/v1")
    return TestClient(app)


@pytest.mark.parametrize("extra,expected,count", [
    ({}, "<not sent>", 0),
    ({"key_features": None}, "<not sent>", 0),
    ({"key_features": ""}, "<empty>", 0),
    ({"key_features": "UDPage,DARdashboard"}, "dardashboard,udpage", 2),
    ({"key_features": ",".join(f"Key{i}" for i in range(30))}, None, 30),  # > 20 keys not cut
])
def test_request_log_contains_key_features(monkeypatch, caplog, extra, expected, count):
    payload = {
        "user_id": "u1", "message": "How to use DAR", "role": "RM",
        "source": "mobile_app", "employee_type": "", "start_conversation": True,
        "session_id": None, **extra,
    }

    with caplog.at_level(logging.INFO, logger="app.audit"):
        with _client(monkeypatch) as client:
            response = client.post(
                "/api/v1/chat/query", json=payload,
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 200
    record = next(r for r in caplog.records if r.getMessage() == "CHAT_REQUEST_RECEIVED")
    details = json.loads(record.details)

    assert details["key_features_count"] == count
    if expected is not None:
        assert details["key_features"] == expected
    else:
        assert len(details["key_features"].split(",")) == count

    # Existing fields still logged; the token never is.
    assert details["role"] == "RM" and details["user_message"] == "How to use DAR"
    assert "test-token" not in record.details
