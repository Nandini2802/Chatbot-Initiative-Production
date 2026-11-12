"""
Ambiguous project -> ask the user to choose instead of the generic
"Could you please provide a little more detail..." reply.

Real case: "Project code for sharukhz residences" matches both
SHAHRUKHZ BY DANUBE and SHAHRUKHZ RESIDENCES BY DANUBE.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.handler_result import HandlerResult
from app.schemas.routing import RoutingIntent, RoutingResult
from app.services import streaming_service as ss
from app.services.project_context_service import (
    ContextDecision,
    format_ambiguous_project_clarification,
    resolve_session_project,
)

SHAH = "SHAHRUKHZ BY DANUBE"
SHAH_RES = "SHAHRUKHZ RESIDENCES BY DANUBE"
ALLOWED = {SHAH, SHAH_RES, "GREENZ BY DANUBE", "OCEANZ BY DANUBE"}
GENERIC = (
    "Could you please provide a little more detail about your project"
    "so I can help you with the right information?"
)


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def test_two_candidates():
    assert format_ambiguous_project_clarification((SHAH, SHAH_RES)) == (
        "I found more than one matching project. "
        f"Did you mean {SHAH} or {SHAH_RES}?"
    )


def test_three_candidates():
    assert format_ambiguous_project_clarification(("A", "B", "C")) == (
        "I found more than one matching project. Did you mean A, B or C?"
    )


def test_capped_at_five_and_deduplicated():
    msg = format_ambiguous_project_clarification(
        ("A", "B", "A", "C", "D", "E", "F", " ", None)
    )
    assert msg.endswith("Did you mean A, B, C, D or E?")


@pytest.mark.parametrize("candidates", [(), None, ("A",), ("A", "A"), ("", " ")])
def test_fewer_than_two_returns_none(candidates):
    assert format_ambiguous_project_clarification(candidates) is None


# ---------------------------------------------------------------------------
# Candidates are carried on the decision
# ---------------------------------------------------------------------------

def test_decision_default_has_no_candidates():
    assert ContextDecision(status="matched").candidates == ()


def test_typo_case_reports_both_shahrukhz_candidates():
    # No router choice, so the ambiguity is reported with its candidates.
    # (With the router's choice it is settled; see test_project_router_tiebreak.py.)
    d = resolve_session_project(
        message="Project code for sharukhz residences",
        router_project=None,
        active_project=None,
        allowed_projects=ALLOWED,
        project_reference_source="explicit",
        explicit_project_reference="sharukhz residences",
    )
    assert d.status == "ambiguous"
    assert set(d.candidates) == {SHAH, SHAH_RES}


@pytest.mark.parametrize("message,ref,expected", [
    ("Project code for shahrukhz residences", "shahrukhz residences", SHAH_RES),
    ("Tell me about greenz", "greenz", "GREENZ BY DANUBE"),
])
def test_matched_cases_unchanged(message, ref, expected):
    d = resolve_session_project(
        message=message,
        router_project=expected,
        active_project=None,
        allowed_projects=ALLOWED,
        project_reference_source="explicit",
        explicit_project_reference=ref,
    )
    assert (d.status, d.project_name, d.candidates) == ("matched", expected, ())


# ---------------------------------------------------------------------------
# End to end through the streaming service
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


def routed(message, ref, source="explicit", project=SHAH_RES, intent="project_information"):
    return RoutingResult(
        language="en",
        requires_clarification=False,
        intents=[RoutingIntent(
            intent=intent,
            project_operation="details" if intent == "project_information" else None,
            original_query=message,
            expanded_query=message,
            action="details",
            project_name=project,
            project_reference_source=source,
            explicit_project_reference=ref,
            unit_number=None,
            bedrooms=None,
            currency=None,
            file_format=None,
            bank_account_types=[],
            marketing_assets=[],
            missing_fields=[],
            requires_clarification=False,
        )],
    )


@pytest.fixture
def stream(monkeypatch):
    calls = []

    monkeypatch.setattr(ss, "load_chat_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(ss, "load_session_project_context", AsyncMock(return_value={}))
    monkeypatch.setattr(ss, "load_previous_inventory_context", AsyncMock(return_value=None))
    monkeypatch.setattr(ss, "load_application_secrets", AsyncMock(return_value={}))
    monkeypatch.setattr(ss, "SalesforceClient", lambda **kw: object())
    monkeypatch.setattr(ss, "InventoryConnector", lambda **kw: SimpleNamespace(
        fetch_inventory=AsyncMock(return_value=SimpleNamespace(projects=[], units=[]))))
    monkeypatch.setattr(ss, "get_inventory_token_service", lambda **kw: SimpleNamespace(
        get_token=AsyncMock(return_value="inv")))
    monkeypatch.setattr(ss, "ProjectCatalogService", lambda **kw: SimpleNamespace(
        get_project_names=AsyncMock(return_value=sorted(ALLOWED))))
    monkeypatch.setattr(ss, "resolve_authorized_units", lambda *a, **k: [])
    monkeypatch.setattr(ss.InventoryCatalogService, "build", staticmethod(
        lambda s: SimpleNamespace(active_projects=sorted(ALLOWED), unit_projects=[])))
    monkeypatch.setattr(ss, "persist_completed_chat", AsyncMock())
    monkeypatch.setattr(ss, "audit_event", lambda *a, **k: None)

    # Record what reaches the project-information handler; stop there.
    from app.handlers import project_information_handler as pih

    async def fake_handle(self, intent):
        calls.append(intent.project_name)
        return HandlerResult(intent="project_information", messages=["HANDLED"], has_data=False)

    monkeypatch.setattr(pih.ProjectInformationHandler, "handle", fake_handle)

    async def run(message, routing_result):
        class FakeRouter:
            def __init__(self, **kw):
                pass

            async def classify(self, **kw):
                return routing_result

        monkeypatch.setattr(ss, "RouterService", FakeRouter)
        events = []
        async for ev in ss._stream_chat_response_impl(
            message=message, session_id=uuid.uuid4(), correlation_id="c",
            user_id="u", role="Agency Admin", source="mobile_app",
            employee_type="",
            clients=SimpleNamespace(redis=FakeRedis(), foundry_openai=object(), postgres=None),
            access_token="tok", walkthrough_engine=SimpleNamespace(guides={}),
            key_features="",
        ):
            events.append(ev)
        return "".join(events)

    return run, calls


@pytest.mark.asyncio
async def test_ambiguous_project_asks_which_one(stream):
    # The router did not choose a project, so nothing settles the
    # ambiguity: the user is asked.
    run, calls = stream
    msg = "Project code for sharukhz residences"
    out = await run(msg, routed(msg, "sharukhz residences", project=None))

    assert "I found more than one matching project." in out
    assert SHAH in out and SHAH_RES in out
    assert "little more detail" not in out
    assert calls == []                      # nothing executed for an ambiguous project


@pytest.mark.asyncio
async def test_ambiguous_typo_settled_by_router_choice(stream):
    # The router chose SHAHRUKHZ RESIDENCES from the official list and it is
    # one of the candidates in the user's message: the request proceeds.
    run, calls = stream
    msg = "Project code for sharukhz residences"
    out = await run(msg, routed(msg, "sharukhz residences"))

    assert calls == [SHAH_RES]
    assert "more than one matching project" not in out


@pytest.mark.asyncio
async def test_router_choice_outside_candidates_still_asks(stream):
    run, calls = stream
    msg = "Project code for sharukhz residences"
    out = await run(msg, routed(msg, "sharukhz residences", project="GREENZ BY DANUBE"))

    assert "I found more than one matching project." in out
    assert calls == []


@pytest.mark.asyncio
async def test_correct_spelling_still_executes(stream):
    run, calls = stream
    msg = "Project code for shahrukhz residences"
    out = await run(msg, routed(msg, "shahrukhz residences"))

    assert calls == [SHAH_RES]
    assert "more than one matching project" not in out


@pytest.mark.asyncio
async def test_unresolved_project_keeps_generic_message(stream):
    run, calls = stream
    msg = "Project code for Shahrukhz Residences"
    # Router reports an explicit project but no reference words -> unresolved_explicit.
    out = await run(msg, routed(msg, None))

    assert "little more detail about your project" in out
    assert "more than one matching project" not in out
    assert calls == []


@pytest.mark.asyncio
async def test_bank_details_never_uses_router_tiebreak(stream, monkeypatch):
    run, calls = stream
    seen = []
    real = ss.resolve_session_project

    def spy(**kwargs):
        seen.append(kwargs.get("allow_router_tiebreak"))
        return real(**kwargs)

    monkeypatch.setattr(ss, "resolve_session_project", spy)

    msg = "Bank details for sharukhz residences"
    out = await run(msg, routed(msg, "sharukhz residences", intent="bank_details"))

    assert seen == [False]
    # No router guess for bank details: the user is asked to choose.
    assert "SHAHRUKHZ RESIDENCES BY DANUBE or SHAHRUKHZ BY DANUBE" in out
    assert "Could you please tell me the project name so I can share the bank details?" not in out
