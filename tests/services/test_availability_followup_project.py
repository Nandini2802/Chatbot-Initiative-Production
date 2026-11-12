"""
Download Availability multi-turn flow.

1. Follow-up replies ("Uae", "Pdf") keep the PENDING request's project.
   Real UAT case: "Download available of greenz" -> "Uae" -> "Pdf" ran for
   OPALZ (the conversation's older active project) instead of GREENZ.
2. A new availability request while one is pending (e.g. "I asked for greenz"
   after a no-report result) keeps the currency/format already given.
3. After a no-report result only very short replies continue the request.

Router results below are the ones the real router returned in UAT logs.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers import availability_handler as ah
from app.handlers import inventory_handler as ih
from app.schemas.handler_result import HandlerResult
from app.schemas.routing import RoutingIntent, RoutingResult
from app.services import streaming_service as ss

GREENZ, OPALZ, OCEANZ = "GREENZ BY DANUBE", "OPALZ BY DANUBE", "OCEANZ 1 BY DANUBE"
NAMES = [GREENZ, OPALZ, OCEANZ]
SESSION = uuid.uuid4()


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)

    def availability_state(self):
        raw = next((v for k, v in self.store.items() if "download-availability" in k), None)
        return json.loads(raw) if raw else None


def availability(message, project=None, currency=None, file_format=None, source="none", ref=None):
    missing = [f for f, v in (("currency", currency), ("file_format", file_format)) if not v]
    if not project:
        missing.append("project_identifier")
    return RoutingResult(language="en", requires_clarification=bool(missing), intents=[RoutingIntent(
        intent="download_availability", original_query=message, expanded_query=message,
        action="download", project_name=project, project_reference_source=source,
        explicit_project_reference=ref, unit_number=None, bedrooms=None, currency=currency,
        file_format=file_format, bank_account_types=[], marketing_assets=[],
        missing_fields=missing, requires_clarification=bool(missing))])


def inventory(message):
    return RoutingResult(language="en", requires_clarification=False, intents=[RoutingIntent(
        intent="inventory", inventory_scope="units", inventory_operation="unit_search",
        original_query=message, expanded_query=message, action="search", project_name=None,
        unit_number=None, bedrooms=2, currency="AED", file_format=None, bank_account_types=[],
        marketing_assets=[], missing_fields=[], requires_clarification=False)])


@pytest.fixture
def chat(monkeypatch):
    redis = FakeRedis()
    executed = []          # (project, currency, format) per availability run
    has_report = {}        # project -> bool

    monkeypatch.setattr(ss, "load_chat_history", AsyncMock(return_value=[]))
    # The conversation's active project is OPALZ (from an earlier brochure request).
    monkeypatch.setattr(ss, "load_session_project_context", AsyncMock(
        return_value={"active_project": {"name": OPALZ}}))
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
    monkeypatch.setattr(ss, "resolve_availability_project", lambda intent, snapshot: SimpleNamespace(
        project_id=f"ID-{intent.project_name}", project_name=intent.project_name))

    async def fake_availability(self, intent):
        executed.append((intent.project_name, intent.currency, intent.file_format))
        if has_report.get(intent.project_name):
            return HandlerResult(intent="download_availability", has_data=True, generation_context={
                "service": "download_availability", "report_generated": True,
                "project_name": intent.project_name, "currency": intent.currency,
                "file_type": intent.file_format, "exchange_rate_text": "", "disclaimer": ""})
        return HandlerResult(intent="download_availability", messages=[
            f"No Download Availability report is currently available for {intent.project_name}."])

    monkeypatch.setattr(ah.AvailabilityHandler, "handle", fake_availability)

    inventory_calls = []

    async def fake_inventory(self, intent):
        inventory_calls.append(intent.inventory_operation)
        return HandlerResult(intent="inventory", messages=["INVENTORY"])

    monkeypatch.setattr(ih.InventoryHandler, "handle", fake_inventory)

    # Inventory filter extraction is an LLM call; return "no extra filters".
    class NoFilters(SimpleNamespace):
        unresolved_terms = []

        def __getattr__(self, name):
            return None

    class FakeExtractor:
        def __init__(self, **kw):
            pass

        async def extract(self, **kw):
            return NoFilters()

    monkeypatch.setattr(ss, "InventoryExtractionService", FakeExtractor)

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

    return SimpleNamespace(say=say, redis=redis, executed=executed,
                           has_report=has_report, inventory_calls=inventory_calls)


# ---------------------------------------------------------------------------
# 1. Follow-ups keep the pending project
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_uat_case_greenz_is_kept_across_uae_and_pdf(chat):
    chat.has_report[GREENZ] = True

    out = await chat.say("Download available of greenz", availability(
        "Download available of greenz", project=GREENZ, source="explicit", ref="greenz"))
    assert "Which currency" in out and chat.executed == []
    assert chat.redis.availability_state()["project_name"] == GREENZ

    # Router returned GREENZ with source "context" (as in UAT).
    out = await chat.say("Uae", availability("Uae", project=GREENZ, currency="AED", source="context"))
    assert chat.executed == []
    assert chat.redis.availability_state()["project_name"] == GREENZ      # was OPALZ (bug)

    await chat.say("Pdf", availability("Pdf", file_format="pdf"))
    assert chat.executed == [(GREENZ, "AED", "pdf")]                      # was OPALZ (bug)


@pytest.mark.asyncio
async def test_new_project_named_in_reply_still_wins(chat):
    await chat.say("availability for greenz", availability(
        "availability for greenz", project=GREENZ, source="explicit", ref="greenz"))
    await chat.say("AED for oceanz 1", availability(
        "AED for oceanz 1", project=OCEANZ, currency="AED", source="explicit", ref="oceanz 1"))
    assert chat.redis.availability_state()["project_name"] == OCEANZ


# ---------------------------------------------------------------------------
# 2. Correction keeps earlier answers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_correction_after_no_report_reuses_currency_and_format(chat):
    chat.has_report[GREENZ] = True
    # Previous attempt ran for OPALZ (AED, pdf) and found no report.
    chat.redis.store[f"danube:download-availability:u:{SESSION}"] = json.dumps({
        "intent": "download_availability", "project_id": "ID-OPALZ", "project_name": OPALZ,
        "currency": "AED", "file_format": "pdf", "after_no_report": True})

    await chat.say("I asked for greenz", availability(
        "I asked for greenz", project=GREENZ, source="explicit", ref="greenz"))
    assert chat.executed == [(GREENZ, "AED", "pdf")]      # no currency/format re-ask


@pytest.mark.asyncio
async def test_new_request_with_its_own_currency_keeps_it(chat):
    chat.redis.store[f"danube:download-availability:u:{SESSION}"] = json.dumps({
        "intent": "download_availability", "project_id": "ID-OPALZ", "project_name": OPALZ,
        "currency": "AED", "file_format": "pdf", "after_no_report": True})

    await chat.say("availability for greenz in USD", availability(
        "availability for greenz in USD", project=GREENZ, currency="USD",
        source="explicit", ref="greenz"))
    assert chat.executed == [(GREENZ, "USD", "pdf")]


@pytest.mark.asyncio
async def test_no_report_result_is_remembered(chat):
    await chat.say("availability for opalz in AED pdf", availability(
        "availability for opalz in AED pdf", project=OPALZ, currency="AED", file_format="pdf",
        source="explicit", ref="opalz"))
    state = chat.redis.availability_state()
    assert (state["project_name"], state["currency"], state["file_format"], state["after_no_report"]) == (
        OPALZ, "AED", "pdf", True)


@pytest.mark.asyncio
async def test_successful_report_clears_state_and_nothing_is_reused(chat):
    chat.has_report[GREENZ] = True
    await chat.say("availability for greenz in AED pdf", availability(
        "availability for greenz in AED pdf", project=GREENZ, currency="AED", file_format="pdf",
        source="explicit", ref="greenz"))
    assert chat.redis.availability_state() is None

    out = await chat.say("availability for oceanz 1", availability(
        "availability for oceanz 1", project=OCEANZ, source="explicit", ref="oceanz 1"))
    assert "Which currency" in out                       # asks as before
    assert chat.executed == [(GREENZ, "AED", "pdf")]


# ---------------------------------------------------------------------------
# 3. After a no-report result, only short replies continue it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_short_reply_retries_in_another_format(chat):
    chat.has_report[OPALZ] = True
    chat.redis.store[f"danube:download-availability:u:{SESSION}"] = json.dumps({
        "intent": "download_availability", "project_id": "ID-OPALZ", "project_name": OPALZ,
        "currency": "AED", "file_format": "pdf", "after_no_report": True})

    await chat.say("Excel", availability("Excel", file_format="excel"))
    assert chat.executed == [(OPALZ, "AED", "excel")]


@pytest.mark.asyncio
async def test_longer_message_after_no_report_is_not_hijacked(chat):
    chat.redis.store[f"danube:download-availability:u:{SESSION}"] = json.dumps({
        "intent": "download_availability", "project_id": "ID-OPALZ", "project_name": OPALZ,
        "currency": "AED", "file_format": "pdf", "after_no_report": True})

    # Contains a currency (AED), which used to be enough to treat a reply as
    # an availability answer. The follow-up decision is made before routing,
    # so the router result here only needs to be a non-availability intent.
    msg = "2 bed units in AED under 2 million"
    out = await chat.say(msg, RoutingResult(language="en", requires_clarification=False, intents=[
        RoutingIntent(intent="greeting", original_query=msg, expanded_query=msg, action="a",
                      project_name=None, unit_number=None, bedrooms=None, currency=None,
                      file_format=None, bank_account_types=[], marketing_assets=[],
                      missing_fields=[], requires_clarification=False)]))
    assert chat.executed == []                           # not run as availability
    assert "Continue my pending" not in out
    assert chat.redis.availability_state() is None       # pending cleared, as before


@pytest.mark.asyncio
async def test_long_reply_during_normal_pending_question_unchanged(chat):
    # While the bot is still asking (no "after_no_report"), the existing
    # rule applies unchanged: a currency reply of up to 10 words continues.
    await chat.say("availability for greenz", availability(
        "availability for greenz", project=GREENZ, source="explicit", ref="greenz"))
    await chat.say("please use AED currency for this report", availability(
        "please use AED currency for this report", project=GREENZ, currency="AED", source="context"))
    state = chat.redis.availability_state()
    assert (state["project_name"], state["currency"]) == (GREENZ, "AED")
