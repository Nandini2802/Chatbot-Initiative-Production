"""
Short project codes (GRZ, DMZ, ETZ-2, ...) built per request from the
user's Units API data (unit.project_code <- ProjectCode__c).
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.routing import RoutingIntent, RoutingResult
from app.services import streaming_service as ss
from app.services.project_codes import (
    build_project_code_map,
    codes_in_project_reference,
    find_project_codes,
    router_code_context,
)
from app.services.project_context_service import resolve_session_project
from app.services.router_service import RouterService

GREENZ, DIAMONDZ = "GREENZ BY DANUBE", "DIAMONDZ BY DANUBE"
ELITZ, ELITZ2, ELITZ3 = "ELITZ BY DANUBE", "ELITZ 2 BY DANUBE", "ELITZ 3 BY DANUBE"
EL2, EL5 = "ELEGANZ 2 BY DANUBE", "ELEGANZ 5 BY DANUBE"


def unit(project, code):
    return SimpleNamespace(project_name=project, project_code=code)


UNITS = [
    unit(GREENZ, "GRZ"), unit(GREENZ, "GRZ"), unit(DIAMONDZ, "DMZ"),
    unit(ELITZ, "ETZ"), unit(ELITZ2, "ETZ-2"), unit(ELITZ3, "ETZ-3"),
    unit(EL2, "ELGZ"), unit(EL5, "ELGZ"),
    unit("BAYZ 102 BY DANUBE", None), unit("SHAHRUKHZ BY DANUBE", ""),
]
CODES = build_project_code_map(UNITS)
ALLOWED = {GREENZ, DIAMONDZ, ELITZ, ELITZ2, ELITZ3, EL2, EL5,
           "BAYZ 102 BY DANUBE", "SHAHRUKHZ BY DANUBE"}


# ---------------------------------------------------------------------------
# Building the lookup
# ---------------------------------------------------------------------------

def test_map_unique_and_shared_codes():
    assert CODES["GRZ"] == (GREENZ,)
    assert CODES["ETZ-2"] == (ELITZ2,)
    assert CODES["ELGZ"] == (EL2, EL5)
    assert "" not in CODES and None not in CODES


def test_code_that_is_another_projects_name_is_dropped():
    codes = build_project_code_map(
        [unit("JEWELZ RESIDENCE", "ELZ")],
        project_names=["ELZ", "JEWELZ RESIDENCE"],
    )
    assert codes == {}


def test_router_context_format():
    ctx = router_code_context(CODES)
    assert ctx["GRZ"] == GREENZ and ctx["ELGZ"] == [EL2, EL5]
    assert router_code_context({}) == {} and router_code_context(None) == {}


# ---------------------------------------------------------------------------
# Finding codes in text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("sales offer for GRZ", (GREENZ,)),
    ("sales offer for grz", (GREENZ,)),
    ("grz?", (GREENZ,)),
    ("project details of DMZ please", (DIAMONDZ,)),
    ("etz 2 project number", (ELITZ2,)),
    ("ETZ-2", (ELITZ2,)),
    ("etz2", (ELITZ2,)),
    ("ETZ", (ELITZ,)),
    ("ELGZ", (EL2, EL5)),
    # Not codes:
    ("GRZ-TH-188", ()),
    ("sales offer for grz-th-188", ()),
    ("ETZ-3-A-F19-1902", ()),
    ("grzx project", ()),
    ("greenz", ()),
    ("", ()),
])
def test_find_project_codes(text, expected):
    assert find_project_codes(text, CODES) == expected


@pytest.mark.parametrize("text,expected", [
    ("GRZ", (GREENZ,)),
    ("GRZ in AED", (GREENZ,)),
    ("ETZ-2", (ELITZ2,)),
    ("ELGZ", (EL2, EL5)),
    ("grz th 188", ()),          # a unit, not a project code
    ("GRZ 188", ()),
    ("greenz", ()),
])
def test_codes_in_project_reference(text, expected):
    assert codes_in_project_reference(text, CODES) == expected


# ---------------------------------------------------------------------------
# Project resolution with codes
# ---------------------------------------------------------------------------

def decide(message, codes=CODES, router=None, source="explicit", ref=None, allowed=ALLOWED):
    return resolve_session_project(
        message=message, router_project=router, active_project=None,
        allowed_projects=allowed, project_reference_source=source,
        explicit_project_reference=ref, project_codes=codes,
    )


def test_unique_code_resolves():
    d = decide("Sales offer for GRZ", ref="GRZ", router=GREENZ)
    assert (d.status, d.project_name, d.should_update_session) == ("matched", GREENZ, True)


def test_code_resolves_even_without_router_project():
    assert decide("project number for DMZ", ref="DMZ").project_name == DIAMONDZ


def test_shared_code_asks():
    d = decide("Sales offer for ELGZ", ref="ELGZ")
    assert d.status == "ambiguous" and set(d.candidates) == {EL2, EL5}


def test_shared_code_router_guess_without_number_still_asks():
    assert decide("Sales offer for ELGZ", ref="ELGZ", router=EL2).status == "ambiguous"


def test_code_for_project_not_allowed_is_ignored():
    d = decide("Sales offer for GRZ", ref="GRZ", allowed=ALLOWED - {GREENZ})
    assert d.status != "matched"


@pytest.mark.parametrize("message,router,ref", [
    ("Tell me about greenz", GREENZ, "greenz"),
    ("project code for shahrukhz", "SHAHRUKHZ BY DANUBE", "shahrukhz"),
])
def test_names_unchanged_with_codes(message, router, ref):
    with_codes = decide(message, router=router, ref=ref)
    without = decide(message, codes=None, router=router, ref=ref)
    assert with_codes == without


def test_without_codes_old_behaviour():
    d = decide("Sales offer for GRZ", codes=None, ref="GRZ")
    assert d.status != "matched"


# ---------------------------------------------------------------------------
# Router input
# ---------------------------------------------------------------------------

def _routing_result():
    return RoutingResult(language="en", requires_clarification=False, intents=[RoutingIntent(
        intent="greeting", original_query="q", expanded_query="q", action="a",
        project_name=None, unit_number=None, bedrooms=None, currency=None,
        file_format=None, bank_account_types=[], marketing_assets=[],
        missing_fields=[], requires_clarification=False)])


@pytest.mark.asyncio
@pytest.mark.parametrize("codes", [CODES, None])
async def test_router_receives_codes_only_when_present(codes):
    seen = {}

    async def parse(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(output_parsed=_routing_result())

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    await RouterService(client=client, model="m").classify(
        message="sales offer for GRZ", project_codes=codes)

    text = str(seen["input"])
    if codes:
        assert '"GRZ": "GREENZ BY DANUBE"' in text
        assert "project_codes maps short project codes" in text
    else:
        assert "project_codes" not in text


# ---------------------------------------------------------------------------
# Streaming: sales offer pre-resolution and bank details
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


def routed(message, intent, ref, project=None):
    return RoutingResult(language="en", requires_clarification=False, intents=[RoutingIntent(
        intent=intent, original_query=message, expanded_query=message, action="a",
        project_name=project, project_reference_source="explicit",
        explicit_project_reference=ref, unit_number=None, bedrooms=None,
        currency=None, file_format=None, bank_account_types=[], marketing_assets=[],
        missing_fields=[], requires_clarification=False)])


@pytest.fixture
def stream(monkeypatch):
    names = sorted(ALLOWED)
    monkeypatch.setattr(ss, "load_chat_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(ss, "load_session_project_context", AsyncMock(return_value={}))
    monkeypatch.setattr(ss, "load_previous_inventory_context", AsyncMock(return_value=None))
    monkeypatch.setattr(ss, "load_application_secrets", AsyncMock(return_value={}))
    monkeypatch.setattr(ss, "SalesforceClient", lambda **kw: object())
    monkeypatch.setattr(ss, "InventoryConnector", lambda **kw: SimpleNamespace(
        fetch_inventory=AsyncMock(return_value=SimpleNamespace(projects=[], units=UNITS))))
    monkeypatch.setattr(ss, "get_inventory_token_service", lambda **kw: SimpleNamespace(
        get_token=AsyncMock(return_value="inv")))
    monkeypatch.setattr(ss, "ProjectCatalogService", lambda **kw: SimpleNamespace(
        get_project_names=AsyncMock(return_value=names)))
    monkeypatch.setattr(ss, "resolve_authorized_units", lambda *a, **k: [])
    monkeypatch.setattr(ss.InventoryCatalogService, "build", staticmethod(
        lambda s: SimpleNamespace(active_projects=names, unit_projects=[])))
    monkeypatch.setattr(ss, "persist_completed_chat", AsyncMock())
    monkeypatch.setattr(ss, "audit_event", lambda *a, **k: None)

    sales_refs, session_calls = [], []

    def fake_sales_offer_project(reference, snapshot):
        sales_refs.append(reference)
        return SimpleNamespace(status="not_found", candidates=(), project=None)

    monkeypatch.setattr(ss, "resolve_sales_offer_project", fake_sales_offer_project)
    real = ss.resolve_session_project

    def spy(**kwargs):
        session_calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(ss, "resolve_session_project", spy)

    async def run(message, routing_result):
        class FakeRouter:
            def __init__(self, **kw):
                pass

            async def classify(self, **kw):
                return routing_result

        monkeypatch.setattr(ss, "RouterService", FakeRouter)
        events = []
        async for ev in ss._stream_chat_response_impl(
            message=message, session_id=uuid.uuid4(), correlation_id="c", user_id="u",
            role="Agency Admin", source="mobile_app", employee_type="",
            clients=SimpleNamespace(redis=FakeRedis(), foundry_openai=object(), postgres=None),
            access_token="tok", walkthrough_engine=SimpleNamespace(guides={}), key_features="",
        ):
            events.append(ev)
        return "".join(events)

    return run, sales_refs, session_calls


@pytest.mark.asyncio
async def test_sales_offer_code_is_resolved_before_sales_offer_lookup(stream):
    run, sales_refs, _ = stream
    msg = "sales offer for GRZ"
    await run(msg, routed(msg, "sales_offer", "GRZ"))
    assert sales_refs == [GREENZ]


@pytest.mark.asyncio
async def test_sales_offer_shared_code_asks(stream):
    run, sales_refs, _ = stream
    msg = "sales offer for ELGZ"
    out = await run(msg, routed(msg, "sales_offer", "ELGZ"))
    assert sales_refs == []
    assert f"Multiple projects match your request. Please specify one: {EL2}, {EL5}." in out


@pytest.mark.asyncio
async def test_sales_offer_name_unchanged(stream):
    run, sales_refs, _ = stream
    msg = "sales offer for greenz"
    await run(msg, routed(msg, "sales_offer", "greenz"))
    assert sales_refs == ["greenz"]


@pytest.mark.asyncio
async def test_bank_details_never_gets_codes(stream):
    run, _, session_calls = stream
    msg = "bank details for GRZ"
    await run(msg, routed(msg, "bank_details", "GRZ"))
    assert session_calls and all(c["project_codes"] is None for c in session_calls)
