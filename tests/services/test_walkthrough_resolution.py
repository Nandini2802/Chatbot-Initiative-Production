"""
Which walkthrough the user means: router pick + aliases + typo-tolerant
match, decided by the user's feature keys. Uses the real workbook and the
real RM key list seen in UAT logs.
"""
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers.walkthrough_handler import WALKTHROUGH_FALLBACK, WalkthroughHandler
from app.schemas.routing import RoutingIntent, RoutingResult
from app.services.router_service import RouterService
from app.services.walkthrough_access_service import WalkthroughEngine
from app.services.walkthrough_feature_resolver import (
    decide_walkthrough,
    find_walkthrough_candidates,
    redirect,
)

ENGINE = WalkthroughEngine(directory=Path("app/data/walkthrough"))
NAMES = [g.name for g in ENGINE.guides.values()]
RM_KEYS = ("HomePage,UnitTab,PDPage,UDPage,CompareUnit,Announcement,MyProfile,Logout,"
           "MarketingList,PrivacyPolicy,TermsConditions,AboutUS,ContactUS,DARCreate,EoiView,"
           "EOICreate,SalesOfferEnable,DownloadAvailability,ChangePassword,AccountList,"
           "DarAnalytics,PitchBrandMorph,PDPBrandMorphLink,EoiAnalytics,Al_AISHA,3DTour")
ALL_KEYS = ",".join(k for g in ENGINE.guides.values() if g.key
                    for k in g.key.replace("|", "/").replace(",", "/").split("/") if k.strip())


def name(fragment):
    return next(n for n in NAMES if fragment.lower() in n.lower())


DAR = name("DAR Analytics")
DAILY = name("Daily Activity Report")


def resolve(message, router=None, keys=RM_KEYS):
    candidates = find_walkthrough_candidates(message, router, NAMES)
    return decide_walkthrough(candidates, lambda n: ENGINE.permission(n, keys)[0])


# ---------------------------------------------------------------------------
# DAR: plain DAR -> Daily Activity Report; DAR Analytics only when asked for
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "How to use DAR", "how to use dar", "Dar dashboard how to use", "dar dashbord",
    "daily activity report", "daily activty report", "where is my dar report",
    "how do I create a DAR", "new dar", "log my dar", "dar create",
])
@pytest.mark.parametrize("router", [None, "Daily Activity Report", "DAR Analytics"])
def test_plain_dar_questions_show_daily_activity_report(message, router):
    d = resolve(message, router)
    assert (d.kind, d.feature) == ("show", DAILY)


@pytest.mark.parametrize("message", [
    "DAR analytics", "how do I check my DAR stats", "dar statistics",
    "where are my dar stories", "how to use dar analitics",
])
@pytest.mark.parametrize("router", [None, "Daily Activity Report", "DAR Analytics"])
def test_explicit_dar_analytics_shows_dar_analytics(message, router):
    d = resolve(message, router)
    assert (d.kind, d.feature) == ("show", DAR)


def test_daily_activity_report_is_no_longer_redirected():
    assert redirect("Daily Activity Report", NAMES) == DAILY
    assert redirect("DAR Analytics", NAMES) == DAR


@pytest.mark.parametrize("keys,expected", [
    ("DARCreate", DAILY),                    # what the app sends
    ("DARView", DAILY),                      # workbook: DARView,DARCreate
    ("dar_view", DAILY),
    ("DARCreate,DarAnalytics", DAILY),       # both keys: plain DAR is still the report
])
def test_dar_access_with_either_key(keys, expected):
    d = resolve("How to use DAR", keys=keys)
    assert (d.kind, d.feature) == ("show", expected)


def test_dar_analytics_key_alone_does_not_open_daily_activity_report():
    d = resolve("How to use DAR", keys="DarAnalytics")
    assert d.kind == "denied"
    assert d.message == "You don't currently have access to Daily Activity Report in your account."


def test_explicit_analytics_with_only_report_key_is_denied():
    d = resolve("dar analytics", keys="DARCreate")
    assert d.kind == "denied"
    assert d.message == "You don't currently have access to DAR Analytics in your account."


def test_dar_without_access_is_an_honest_denial():
    d = resolve("How to use DAR", keys="UDPage,CompareUnit")
    assert d.kind == "denied"
    assert d.message == "You don't currently have access to Daily Activity Report in your account."


# ---------------------------------------------------------------------------
# Ambiguity and access
# ---------------------------------------------------------------------------

def test_generic_word_asks_among_accessible_features():
    d = resolve("how to download", router=name("Download Sales Offer"))
    assert d.kind == "ask"
    assert set(d.options) == {name("Download Availability"), name("Download Project Brochure"),
                              name("Download Sales Offer")}
    assert d.message.startswith("Which one do you need help with:")


def test_ambiguous_but_only_one_accessible_shows_it():
    # "profile": My Profile (allowed) vs Company Profile (AgencyProfile - not allowed)
    d = resolve("how to update profile", router=name("My Profile"))
    assert (d.kind, d.feature) == ("show", name("My Profile"))


def test_ask_lists_only_accessible_options():
    d = resolve("how to download", router=name("Download Sales Offer"), keys="SalesOfferEnable,DownloadAvailability")
    assert d.kind == "ask"
    assert all(ENGINE.permission(o, "SalesOfferEnable,DownloadAvailability")[0] for o in d.options)


def test_feature_without_access_is_denied_by_name():
    d = resolve("how to create a lead", router=name("Create Lead"))
    assert d.kind == "denied"
    assert d.message == "You don't currently have access to Create Lead in your account."


@pytest.mark.parametrize("message,fragment", [
    ("how to compare units", "Add a Unit to Compare"),
    ("bank details", "Bank Details for Projects"),
    ("3d tour", "3D Tour"),
    ("how to raise an eoi", "EOI"),
    ("how to chnge pasword", "Change Password"),   # typos
    ("how to logout", "Log Out"),
])
def test_aliases_and_typos_without_router(message, fragment):
    d = resolve(message, router=None, keys=ALL_KEYS)
    assert (d.kind, d.feature) == ("show", name(fragment))


def test_nothing_matched():
    d = resolve("how to fly a kite", router=None)
    assert d.kind == "none"


def test_every_walkthrough_by_exact_name_unchanged():
    """Regression: asking for any walkthrough by name gives that walkthrough."""
    for n in NAMES:
        for message in (f"how to use {n}", n):
            d = resolve(message, router=n, keys=ALL_KEYS)
            assert (d.kind, d.feature) == ("show", redirect(n, NAMES)), (message, d)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handler(message, keys=RM_KEYS):
    h = WalkthroughHandler(engine=ENGINE, key_features=keys, role="RM",
                           redis_client=None, message=message)
    h.video_service = SimpleNamespace(
        find_videos=AsyncMock(return_value=[]),
        find_permitted_videos=AsyncMock(return_value=[]),
    )
    return h


@pytest.mark.asyncio
async def test_handler_dar_returns_daily_activity_report_steps():
    result = await handler("How to use DAR").handle(SimpleNamespace(feature_name="Daily Activity Report"))
    assert result.has_data is True
    assert result.generation_context["feature_name"] == DAILY
    assert result.generation_context["approved_steps"]


@pytest.mark.asyncio
async def test_handler_router_picking_analytics_for_plain_dar_gives_the_report():
    result = await handler("How to use DAR").handle(SimpleNamespace(feature_name="DAR Analytics"))
    assert result.generation_context["feature_name"] == DAILY


@pytest.mark.asyncio
async def test_handler_explicit_analytics_gives_dar_analytics_steps():
    result = await handler("show me dar analytics").handle(SimpleNamespace(feature_name="DAR Analytics"))
    assert result.generation_context["feature_name"] == DAR


@pytest.mark.asyncio
async def test_handler_asks_when_ambiguous():
    result = await handler("how to download").handle(SimpleNamespace(feature_name=name("Download Sales Offer")))
    assert result.has_data is False
    assert result.messages[0].startswith("Which one do you need help with:")


@pytest.mark.asyncio
async def test_handler_unknown_feature_keeps_fallback():
    result = await handler("how to fly a kite").handle(SimpleNamespace(feature_name=None))
    assert result.messages == [WALKTHROUGH_FALLBACK]


# ---------------------------------------------------------------------------
# Router fallback: the router did not name a walkthrough
# ---------------------------------------------------------------------------

def _walkthrough_result(feature, clarify):
    return RoutingResult(language="en", requires_clarification=clarify, intents=[RoutingIntent(
        intent="excel_walkthrough", feature_name=feature, original_query="q", expanded_query="q",
        action="a", project_name=None, unit_number=None, bedrooms=None, currency=None,
        file_format=None, bank_account_types=[], marketing_assets=[],
        missing_fields=(["feature_name"] if clarify else []), requires_clarification=clarify)])


async def _classify(message, llm_result):
    async def parse(**kw):
        return SimpleNamespace(output_parsed=llm_result)

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    return await RouterService(client=client, model="m").classify(
        message=message, walkthrough_features=NAMES)


@pytest.mark.asyncio
async def test_router_fills_missing_feature_from_typo():
    r = await _classify("how to use dar dashbord", _walkthrough_result(None, True))
    item = r.intents[0]
    assert item.feature_name == DAILY
    assert item.requires_clarification is False and "feature_name" not in item.missing_fields


@pytest.mark.asyncio
async def test_router_still_flags_unknown_feature():
    r = await _classify("how to fly a kite", _walkthrough_result(None, True))
    assert r.intents[0].feature_name is None and r.intents[0].requires_clarification is True


@pytest.mark.asyncio
async def test_router_keeps_valid_pick():
    r = await _classify("how to compare units", _walkthrough_result(name("Add a Unit to Compare"), False))
    assert r.intents[0].feature_name == name("Add a Unit to Compare")


# ---------------------------------------------------------------------------
# Streaming: an unknown walkthrough no longer gets the "project" message
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


@pytest.mark.asyncio
async def test_stream_unknown_walkthrough_message(monkeypatch):
    from app.services import streaming_service as ss

    for attr, value in [("load_chat_history", AsyncMock(return_value=[])),
                        ("load_session_project_context", AsyncMock(return_value={})),
                        ("load_previous_inventory_context", AsyncMock(return_value=None)),
                        ("load_application_secrets", AsyncMock(return_value={})),
                        ("persist_completed_chat", AsyncMock())]:
        monkeypatch.setattr(ss, attr, value)
    monkeypatch.setattr(ss, "SalesforceClient", lambda **kw: object())
    monkeypatch.setattr(ss, "InventoryConnector", lambda **kw: SimpleNamespace(
        fetch_inventory=AsyncMock(return_value=SimpleNamespace(projects=[], units=[]))))
    monkeypatch.setattr(ss, "get_inventory_token_service", lambda **kw: SimpleNamespace(
        get_token=AsyncMock(return_value="i")))
    monkeypatch.setattr(ss, "ProjectCatalogService", lambda **kw: SimpleNamespace(
        get_project_names=AsyncMock(return_value=["GREENZ BY DANUBE"])))
    monkeypatch.setattr(ss, "resolve_authorized_units", lambda *a, **k: [])
    monkeypatch.setattr(ss.InventoryCatalogService, "build", staticmethod(
        lambda s: SimpleNamespace(active_projects=["GREENZ BY DANUBE"], unit_projects=[])))
    monkeypatch.setattr(ss, "audit_event", lambda *a, **k: None)

    class FakeRouter:
        def __init__(self, **kw):
            pass

        async def classify(self, **kw):
            return _walkthrough_result(None, True)

    monkeypatch.setattr(ss, "RouterService", FakeRouter)
    out = []
    async for ev in ss._stream_chat_response_impl(
        message="how to fly a kite", session_id=uuid.uuid4(), correlation_id="c", user_id="u",
        role="RM", source="mobile_app", employee_type="",
        clients=SimpleNamespace(redis=FakeRedis(), foundry_openai=object(), postgres=None),
        access_token="t", walkthrough_engine=SimpleNamespace(guides={}), key_features=RM_KEYS,
    ):
        out.append(ev)
    text = "".join(out)
    assert "we don't offer that feature yet" in text
    assert "about your project" not in text
