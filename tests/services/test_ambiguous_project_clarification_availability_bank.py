"""
Ambiguous project names in Download Availability and Bank Details.

UAT case: "Bayz" matches BAYZ 101 and BAYZ 102. The resolver prepared
"Did you mean BAYZ 101 BY DANUBE or BAYZ 102 BY DANUBE?", but both flows
replied with their fixed "Which project...?" sentence, so the user was
asked the same question again and again.

Now: the "Did you mean ..." question is shown when one was prepared;
every other clarification keeps its exact existing wording.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers import availability_handler as ah
from app.handlers import bank_details_handler as bh
from app.schemas.handler_result import HandlerResult
from app.schemas.routing import RoutingIntent, RoutingResult
from app.services import streaming_service as ss

GREENZ, BREEZE = "GREENZ BY DANUBE", "BREEZE BY DANUBE"
BAYZ101, BAYZ102 = "BAYZ 101 BY DANUBE", "BAYZ 102 BY DANUBE"
NAMES = [GREENZ, BREEZE, BAYZ101, BAYZ102]

WHICH_PROJECT = "Which Danube project would you like the availability report for?"
WHICH_CURRENCY = "Which currency would you like for the availability report?"
WHICH_FORMAT = "Would you like the report in PDF or Excel format?"
BANK_PROJECT = "Could you please tell me the project name so I can share the bank details?"


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


def availability(message, project=None, currency=None, file_format=None, source="none", ref=None):
    missing = [f for f, v in (("currency", currency), ("file_format", file_format)) if not v]
    if not project:
        missing += ["project_identifier", "project_name"]
    return RoutingResult(language="en", requires_clarification=bool(missing), intents=[RoutingIntent(
        intent="download_availability", original_query=message, expanded_query=message,
        action="download", project_name=project, project_reference_source=source,
        explicit_project_reference=ref, unit_number=None, bedrooms=None, currency=currency,
        file_format=file_format, bank_account_types=[], marketing_assets=[],
        missing_fields=missing, requires_clarification=bool(missing))])


def bank(message, project=None, source="none", ref=None):
    return RoutingResult(language="en", requires_clarification=False, intents=[RoutingIntent(
        intent="bank_details", original_query=message, expanded_query=message,
        action="get", project_name=project, project_reference_source=source,
        explicit_project_reference=ref, unit_number=None, bedrooms=None, currency=None,
        file_format=None, bank_account_types=[], marketing_assets=[],
        missing_fields=[], requires_clarification=False)])


@pytest.fixture
def chat(monkeypatch):
    redis = FakeRedis()
    executed = []

    monkeypatch.setattr(ss, "load_chat_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(ss, "load_session_project_context", AsyncMock(
        return_value={"active_project": {"name": BREEZE}}))
    monkeypatch.setattr(ss, "load_previous_inventory_context", AsyncMock(return_value=None))
    monkeypatch.setattr(ss, "load_application_secrets", AsyncMock(return_value={}))
    monkeypatch.setattr(ss, "SalesforceClient", lambda **kw: object())
    monkeypatch.setattr(ss, "InventoryConnector", lambda **kw: SimpleNamespace(
        fetch_inventory=AsyncMock(return_value=SimpleNamespace(projects=[], units=[]))))
    monkeypatch.setattr(ss, "get_inventory_token_service", lambda **kw: SimpleNamespace(
        get_token=AsyncMock(return_value="inv")))
    monkeypatch.setattr(ss, "ProjectCatalogService", lambda **kw: SimpleNamespace(
        get_project_names=AsyncMock(return_value=NAMES)))
    monkeypatch.setattr(ss, "resolve_authorized_units", lambda *a, **k: [])
    monkeypatch.setattr(ss.InventoryCatalogService, "build", staticmethod(
        lambda s: SimpleNamespace(active_projects=NAMES, unit_projects=[])))
    monkeypatch.setattr(ss, "persist_completed_chat", AsyncMock())
    monkeypatch.setattr(ss, "audit_event", lambda *a, **k: None)
    def fake_resolve(intent, snapshot):
        # Like the real resolver: no project -> error.
        if not intent.project_name:
            raise ss.AvailabilityResolutionError("Please specify the project.")
        return SimpleNamespace(project_id=f"ID-{intent.project_name}",
                               project_name=intent.project_name)

    monkeypatch.setattr(ss, "resolve_availability_project", fake_resolve)

    async def fake_availability(self, intent):
        executed.append(("availability", intent.project_name, intent.currency, intent.file_format))
        return HandlerResult(intent="download_availability", has_data=True, generation_context={
            "service": "download_availability", "report_generated": True,
            "project_name": intent.project_name, "currency": intent.currency,
            "file_type": intent.file_format, "exchange_rate_text": "", "disclaimer": ""})

    async def fake_bank(self, intent):
        executed.append(("bank", intent.project_name))
        return HandlerResult(intent="bank_details", messages=[f"BANK {intent.project_name}"])

    monkeypatch.setattr(ah.AvailabilityHandler, "handle", fake_availability)
    monkeypatch.setattr(bh.BankDetailsHandler, "handle", fake_bank)

    async def say(message, routed):
        class FakeRouter:
            def __init__(self, **kw):
                pass

            async def classify(self, **kw):
                return routed

        monkeypatch.setattr(ss, "RouterService", FakeRouter)
        out = []
        async for ev in ss._stream_chat_response_impl(
            message=message, session_id=SESSION, correlation_id="c", user_id="u",
            role="RM", source="mobile_app", employee_type="",
            clients=SimpleNamespace(redis=redis, foundry_openai=object(), postgres=None),
            access_token="tok", walkthrough_engine=SimpleNamespace(guides={}),
            key_features="DownloadAvailability",
        ):
            out.append(ev)
        return "".join(out)

    return SimpleNamespace(say=say, redis=redis, executed=executed)


SESSION = uuid.uuid4()
DID_YOU_MEAN = f"{BAYZ101} or {BAYZ102}"


def preset_pending(chat, **state):
    chat.redis.store[f"danube:download-availability:u:{SESSION}"] = json.dumps({
        "intent": "download_availability", **state})


# ---------------------------------------------------------------------------
# Download Availability
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_uat_case_bayz_asks_which_bayz(chat):
    """'Bayz' after a no-report result: show the two options, not the generic question."""
    preset_pending(chat, project_id="ID-BREEZE", project_name=BREEZE,
                   currency="AED", file_format="pdf", after_no_report=True)

    out = await chat.say("Bayz", availability("Bayz", source="explicit", ref="Bayz"))

    assert DID_YOU_MEAN in out
    assert WHICH_PROJECT not in out
    assert chat.executed == []


@pytest.mark.asyncio
async def test_uat_case_picking_bayz_101_reuses_aed_pdf(chat):
    preset_pending(chat, project_id="ID-BREEZE", project_name=BREEZE,
                   currency="AED", file_format="pdf", after_no_report=True)
    await chat.say("Bayz", availability("Bayz", source="explicit", ref="Bayz"))

    # Router result as in UAT for a bare project reply: no currency/format.
    await chat.say("Bayz 101", availability("Bayz 101", project=BAYZ101,
                                            source="explicit", ref="Bayz 101"))
    assert chat.executed == [("availability", BAYZ101, "AED", "pdf")]


@pytest.mark.asyncio
async def test_bayz_ambiguous_without_pending_request(chat):
    out = await chat.say("Bayz", availability("Bayz", source="explicit", ref="Bayz"))
    assert DID_YOU_MEAN in out and WHICH_PROJECT not in out


@pytest.mark.asyncio
async def test_unknown_project_keeps_existing_question(chat):
    """'bayz altseat' does not resolve (not ambiguous): wording unchanged."""
    out = await chat.say("Give for bayz altseat", availability(
        "Give for bayz altseat", currency="AED", file_format="pdf",
        source="explicit", ref="bayz altseat"))
    assert WHICH_PROJECT in out and DID_YOU_MEAN not in out


@pytest.mark.asyncio
async def test_no_project_keeps_existing_question(chat, monkeypatch):
    # No active project in the conversation either.
    monkeypatch.setattr(ss, "load_session_project_context", AsyncMock(return_value={}))
    out = await chat.say("download availability", availability("download availability"))
    assert WHICH_PROJECT in out


@pytest.mark.asyncio
async def test_currency_question_unchanged(chat):
    out = await chat.say("availability for greenz", availability(
        "availability for greenz", project=GREENZ, source="explicit", ref="greenz"))
    assert WHICH_CURRENCY in out


@pytest.mark.asyncio
async def test_format_question_unchanged(chat):
    out = await chat.say("availability for greenz in AED", availability(
        "availability for greenz in AED", project=GREENZ, currency="AED",
        source="explicit", ref="greenz"))
    assert WHICH_FORMAT in out


@pytest.mark.asyncio
async def test_exact_bayz_101_runs_report(chat):
    await chat.say("availability for bayz 101 AED pdf", availability(
        "availability for bayz 101 AED pdf", project=BAYZ101, currency="AED",
        file_format="pdf", source="explicit", ref="bayz 101"))
    assert chat.executed == [("availability", BAYZ101, "AED", "pdf")]


# ---------------------------------------------------------------------------
# Bank Details
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bank_details_bayz_asks_which_bayz(chat):
    out = await chat.say("bank details for bayz", bank(
        "bank details for bayz", source="explicit", ref="bayz"))
    assert DID_YOU_MEAN in out and BANK_PROJECT not in out
    assert chat.executed == []


@pytest.mark.asyncio
async def test_bank_details_unknown_project_keeps_existing_question(chat):
    out = await chat.say("bank details for xyzzy", bank(
        "bank details for xyzzy", source="explicit", ref="xyzzy"))
    assert BANK_PROJECT in out and DID_YOU_MEAN not in out


@pytest.mark.asyncio
async def test_bank_details_exact_project_unchanged(chat):
    await chat.say("bank details for greenz", bank(
        "bank details for greenz", project=GREENZ, source="explicit", ref="greenz"))
    assert chat.executed == [("bank", GREENZ)]
