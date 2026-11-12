"""
Specific project questions answered from the Projects API
(project_information / project_operation = "field").
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers import project_information_handler as pih
from app.schemas.routing import RoutingIntent, RoutingResult
from app.services import streaming_service as ss
from app.services.project_fields import (
    TOTAL_FIELDS,
    build_field_answer,
    expand_fields,
    field_rows,
    format_field_value,
)
from app.services.router_service import RouterService
from app.services.template_service import TemplateService


class Rec(SimpleNamespace):
    """Record whose unset attributes are None."""

    def __getattr__(self, name):
        return None


BREEZE = Rec(
    project_id="a14FV000007XAuDYAW", project_name="BREEZE BY DANUBE",
    project_number="3456", project_configuration="B+G+8P+P+48+RT",
    places_nearby=None, location="Dubai Maritime City, Dubai",
    completion_date="2029", handover_date=None, payment_plan="Pay 1% Monthly",
    starting_price="", total_units=1199, total_sold_units=1, total_booked_units=1,
    total_residential_units=0, total_other_units=38, total_new_units=1158,
    total_buildings=1, total_floors=None, total_commercial_units=0,
    total_bua_sqft=None, total_saleable_area=2739661000,
    unit_of_measurement="Square Feet", total_selling_price=999,
    enable_brandmorph_pitch=False,
)
GREENZ = Rec(project_id="P-GRZ", project_name="GREENZ BY DANUBE", project_number="1234",
             starting_price="4800000.00", handover_date="2030-07-01")
UNITS = [
    Rec(unit_id="U1", project_id="P-GRZ", project_name="GREENZ BY DANUBE", project_code="GRZ"),
    Rec(unit_id="U2", project_id="P-GRZ", project_name="GREENZ BY DANUBE", project_code="GRZ"),
    Rec(unit_id="U3", project_id="X", project_name="OTHER", project_code="OTH"),
]


# ---------------------------------------------------------------------------
# Catalogue and formatting
# ---------------------------------------------------------------------------

def test_expand_fields():
    assert expand_fields(["project_number", "project_number", "bogus"]) == ["project_number"]
    assert expand_fields(["all_totals"]) == list(TOTAL_FIELDS)
    assert expand_fields([]) == [] and expand_fields(None) == []


def test_excluded_fields_never_returned():
    assert expand_fields([
        "total_selling_price", "enable_brandmorph_pitch", "total_available_units",
        "eoi_active", "project_web_id",
    ]) == []


@pytest.mark.parametrize("field,value,expected", [
    ("total_units", 1199, "1,199"),
    ("total_saleable_area", 2739661000, "2,739,661,000 square feet"),
    ("starting_price", "4800000.00", "AED 4,800,000"),
    ("starting_price", "", None),
    ("places_nearby", None, None),
    ("project_configuration", "B+G+8P+P+48+RT", "B+G+8P+P+48+RT"),
    ("location", ["A", "B"], "A, B"),
])
def test_format_field_value(field, value, expected):
    assert format_field_value(field, value, BREEZE) == expected


def test_project_code_and_number_requested_together_give_one_field():
    assert expand_fields(["project_number", "project_code"]) == ["project_code"]
    assert expand_fields(["project_code", "project_number"]) == ["project_code"]
    assert expand_fields(["project_number"]) == ["project_number"]


def test_project_code_comes_from_projects_api_project_number():
    # Units API codes (e.g. GRZ) are never used for the answer.
    rows = field_rows(GREENZ, ["project_code"])
    assert rows == [{"field": "project_code", "label": "project code", "value": "1234"}]


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------

def answer(project, fields):
    return build_field_answer(project.project_name, field_rows(project, expand_fields(fields)))


def test_single_field_answer():
    assert answer(BREEZE, ["project_number"]) == "The project number for BREEZE BY DANUBE is 3456."
    assert answer(GREENZ, ["handover_date"]) == "The handover date for GREENZ BY DANUBE is 2030-07-01."


def test_missing_value_answer():
    assert answer(BREEZE, ["places_nearby"]) == "Places nearby isn't available for BREEZE BY DANUBE."


def test_project_code_answer_is_the_project_number():
    # The router asks for both fields for "project code" questions.
    assert answer(BREEZE, ["project_number", "project_code"]) == (
        "The project code for BREEZE BY DANUBE is 3456.")
    assert answer(GREENZ, ["project_code"]) == (
        "The project code for GREENZ BY DANUBE is 1234.")


def test_project_code_missing_number():
    no_number = Rec(project_name="ELEGANZ 2 BY DANUBE", project_number=None)
    assert answer(no_number, ["project_number", "project_code"]) == (
        "Project code isn't available for ELEGANZ 2 BY DANUBE.")


def test_many_fields_answer():
    assert answer(BREEZE, ["all_totals"]) == "Here are the requested details for BREEZE BY DANUBE."


def test_card_renders_and_escapes():
    rows = field_rows(BREEZE, ["project_number", "places_nearby"])
    rows.append({"field": "x", "label": "<b>x</b>", "value": "<script>1</script>"})
    html = TemplateService().render("project_fields.html.j2", project_name="BREEZE & CO", rows=rows)
    assert "3456" in html and "Not available" in html
    assert "BREEZE &amp; CO" in html
    assert "<script>1" not in html and "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def make_handler(projects=(BREEZE, GREENZ)):
    handler = pih.ProjectInformationHandler(
        inventory_snapshot=SimpleNamespace(units=UNITS, projects=[]),
        inventory_token="inv", access_token="tok",
    )

    async def fetch_projects(**kw):
        return list(projects)

    async def no_coordinates(*a, **k):
        return {}

    handler.connector = SimpleNamespace(fetch_projects=fetch_projects)
    handler.get_project_map_urls = no_coordinates
    return handler


def field_intent(name, fields, operation="field"):
    return SimpleNamespace(
        project_operation=operation, project_fields=fields, project_name=name,
        project_id=None, project_number=None, unit_id=None, unit_name=None,
        unit_number=None, project_limit=None, project_location=None,
    )


@pytest.mark.asyncio
async def test_handler_field_answer_and_card():
    result = await make_handler().handle(field_intent("BREEZE BY DANUBE", ["project_number"]))
    assert result.messages == ["The project number for BREEZE BY DANUBE is 3456."]
    assert [b["card_type"] for b in result.html_blocks] == ["project_fields"]
    assert result.generation_context["operation"] == "field"
    assert result.has_data is True


@pytest.mark.asyncio
async def test_handler_project_code_for_breeze():
    # As routed for "Project code for breeze" (router sends both fields).
    result = await make_handler().handle(
        field_intent("BREEZE BY DANUBE", ["project_number", "project_code"]))
    assert result.messages == ["The project code for BREEZE BY DANUBE is 3456."]
    html = result.html_blocks[0]["html"]
    assert html.count('class="pf-row"') == 1
    assert "Project code" in html and "3456" in html
    assert "Not available" not in html
    assert result.generation_context["fields"] == ["project_code"]


@pytest.mark.asyncio
async def test_handler_unknown_project_uses_existing_error():
    result = await make_handler().handle(field_intent("NOT A PROJECT", ["project_number"]))
    assert result.has_data is False and result.messages


@pytest.mark.asyncio
async def test_handler_field_without_fields_shows_details_card():
    result = await make_handler().handle(field_intent("BREEZE BY DANUBE", []))
    assert [b["card_type"] for b in result.html_blocks] == ["project_details"]
    assert result.generation_context["operation"] == "details"


@pytest.mark.asyncio
async def test_handler_details_unchanged():
    result = await make_handler().handle(field_intent("BREEZE BY DANUBE", [], operation="details"))
    assert [b["card_type"] for b in result.html_blocks] == ["project_details"]
    assert result.messages == []


# ---------------------------------------------------------------------------
# Router schema / validation
# ---------------------------------------------------------------------------

def routing(**fields):
    base = dict(intent="project_information", original_query="q", expanded_query="q",
                action="a", project_name=None, unit_number=None, bedrooms=None,
                currency=None, file_format=None, bank_account_types=[],
                marketing_assets=[], missing_fields=[], requires_clarification=False)
    base.update(fields)
    return RoutingResult(language="en", intents=[RoutingIntent(**base)],
                         requires_clarification=False)


def test_schema_default_and_existing_operations():
    for op in ["latest", "list", "details", "location_search", "tour", "amenities", "faq", "field"]:
        assert routing(project_operation=op).intents[0].project_fields == []


def test_schema_rejects_unknown_field():
    with pytest.raises(Exception):
        routing(project_operation="field", project_fields=["total_selling_price"])


def test_validate_field_with_project():
    r = RouterService.validate_routing(routing(
        project_operation="field", project_fields=["all_totals"], project_name="GREENZ BY DANUBE"))
    item = r.intents[0]
    assert item.project_operation == "field"
    assert item.project_fields == list(TOTAL_FIELDS)
    assert item.requires_clarification is False


def test_validate_field_without_project_asks():
    r = RouterService.validate_routing(routing(project_operation="field", project_fields=["project_number"]))
    assert "project_identifier" in r.intents[0].missing_fields


def test_validate_field_without_fields_becomes_details():
    r = RouterService.validate_routing(routing(
        project_operation="field", project_fields=[], project_name="GREENZ BY DANUBE"))
    assert r.intents[0].project_operation == "details"


# ---------------------------------------------------------------------------
# End to end through the streaming service (no LLM for the answer)
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
async def test_stream_field_answer(monkeypatch):
    names = ["BREEZE BY DANUBE", "GREENZ BY DANUBE"]
    persisted = AsyncMock()
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
    monkeypatch.setattr(ss, "persist_completed_chat", persisted)
    monkeypatch.setattr(ss, "audit_event", lambda *a, **k: None)

    async def fetch_projects(self, **kw):
        return [BREEZE, GREENZ]

    monkeypatch.setattr(pih.ProjectInformationConnector, "fetch_projects", fetch_projects)

    msg = "Project number for Breeze"
    routed = routing(project_operation="field", project_fields=["project_number"],
                     project_name="BREEZE BY DANUBE", project_reference_source="explicit",
                     explicit_project_reference="Breeze", original_query=msg, expanded_query=msg)

    class FakeRouter:
        def __init__(self, **kw):
            pass

        async def classify(self, **kw):
            return routed

    monkeypatch.setattr(ss, "RouterService", FakeRouter)

    events = []
    async for ev in ss._stream_chat_response_impl(
        message=msg, session_id=uuid.uuid4(), correlation_id="c", user_id="u",
        role="Agency Admin", source="mobile_app", employee_type="",
        clients=SimpleNamespace(redis=FakeRedis(), foundry_openai=object(), postgres=None),
        access_token="tok", walkthrough_engine=SimpleNamespace(guides={}), key_features="",
    ):
        events.append(ev)
    out = "".join(events)

    assert "event: error" not in out, out
    assert "project number" in out and "3456" in out
    assert '"card_type": "project_fields"' in out
    saved = persisted.await_args.kwargs["assistant_message"]
    assert saved == "The project number for BREEZE BY DANUBE is 3456."
    assert "Project details displayed in HTML card" not in out + saved
