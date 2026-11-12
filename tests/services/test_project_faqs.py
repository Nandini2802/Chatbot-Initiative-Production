"""
Project FAQs (OSF Portfolio -> project_information / faq).

Covers:
- HTML cleaning of CMS answers (no raw HTML ever reaches the card)
- FAQ extraction from OSF records (top level or under "meta")
- Card template rendering and escaping
- Handler: success, project without FAQs, OSF failure, unknown project,
  and dispatch through handle()
- Router: FAQ safety net and validation, including cases that must
  stay unchanged
"""
from types import SimpleNamespace

import pytest

from app.handlers.project_information_handler import ProjectInformationHandler
from app.schemas.routing import RoutingIntent, RoutingResult
from app.services.router_service import RouterService
from app.services.template_service import TemplateService
from app.utils.project_faqs import (
    extract_project_faqs,
    find_faq_entries,
    html_to_blocks,
    html_to_text,
)

# Sample taken from the OSF response format (Oceanz).
OCEANZ_FAQS = [
    {
        "danube_faqs_title": "What type of properties are available at Oceanz by Danube?",
        "danube_faqs_content": "<p>Oceanz by Danube offers a range of luxurious residences, including studios, 1, 2, and 3-bedroom apartments, and even a limited collection of Oceanic Villas.</p>\n",
    },
    {
        "danube_faqs_title": "When is the expected completion date for Oceanz by Danube?",
        "danube_faqs_content": "<p>Currently under construction, the project is expected to deliver new homes by Q1 2027</p>\n",
    },
    {
        "danube_faqs_title": "What are the unique features of Oceanz by Danube?",
        "danube_faqs_content": "<ul data-sourcepos=\"13:1-16:0\">\n<li data-sourcepos=\"13:1-13:26\">Breathtaking ocean views</li>\n<li data-sourcepos=\"15:1-16:0\">Luxury amenities like a floating cinema, infinity pool, and spa facilities</li>\n</ul>\n<p>&nbsp;</p>\n",
    },
    {
        "danube_faqs_title": "Is Dubai Maritime City a good place to live?",
        "danube_faqs_content": "<p>Dubai Maritime City offers a unique waterfront living experience. Whether you&#8217;re seeking a vibrant urban lifestyle or a peaceful waterfront haven, it may be suitable.</p>\n",
    },
]


# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------

def test_paragraph_to_text():
    blocks = html_to_blocks("<p>Hello <strong>world</strong></p>\n")
    assert blocks == [{"type": "paragraph", "text": "Hello world"}]


def test_list_attributes_dropped_and_empty_nbsp_paragraph_skipped():
    blocks = html_to_blocks(OCEANZ_FAQS[2]["danube_faqs_content"])
    assert blocks == [{
        "type": "list",
        "items": [
            "Breathtaking ocean views",
            "Luxury amenities like a floating cinema, infinity pool, and spa facilities",
        ],
    }]


def test_entities_decoded():
    text = html_to_text(OCEANZ_FAQS[3]["danube_faqs_content"])
    assert "you’re" in text
    assert "&#8217;" not in text


def test_script_and_style_removed():
    blocks = html_to_blocks(
        "<p>Safe</p><script>alert('x')</script><style>p{}</style><p>Also safe</p>"
    )
    texts = [b["text"] for b in blocks]
    assert texts == ["Safe", "Also safe"]


def test_tags_in_text_never_survive():
    blocks = html_to_blocks('<p onclick="x()">A <img src=x onerror=alert(1)> B</p>')
    assert blocks == [{"type": "paragraph", "text": "A B"}]


def test_empty_or_non_string():
    assert html_to_blocks("") == []
    assert html_to_blocks(None) == []
    assert html_to_blocks(123) == []


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_find_entries_top_level_and_meta():
    assert find_faq_entries({"danube_faqs_title_and_content": [1]}) == [1]
    assert find_faq_entries({"meta": {"danube_faqs_title_and_content": [2]}}) == [2]
    assert find_faq_entries({"meta": {}}) == []
    assert find_faq_entries("not a dict") == []


def test_extract_all_faqs_in_order():
    faqs = extract_project_faqs(
        [{"title": "Oceanz by Danube",
          "meta": {"danube_faqs_title_and_content": OCEANZ_FAQS}}]
    )
    assert [f["question"] for f in faqs] == [
        e["danube_faqs_title"] for e in OCEANZ_FAQS
    ]
    assert faqs[2]["answer"][0]["type"] == "list"


def test_extract_skips_invalid_and_duplicates():
    entries = [
        {"danube_faqs_title": "Q1?", "danube_faqs_content": "<p>A1</p>"},
        {"danube_faqs_title": "q1?", "danube_faqs_content": "<p>dup</p>"},
        {"danube_faqs_title": "", "danube_faqs_content": "<p>no question</p>"},
        {"danube_faqs_title": "No answer?", "danube_faqs_content": "<p>&nbsp;</p>"},
        "garbage",
    ]
    faqs = extract_project_faqs([{"danube_faqs_title_and_content": entries}])
    assert [f["question"] for f in faqs] == ["Q1?"]


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

def test_template_renders_and_escapes():
    faqs = [
        {"question": "<script>alert(1)</script> Q?",
         "answer": [{"type": "paragraph", "text": "<b>bold</b>"},
                    {"type": "list", "items": ["one", "<i>two</i>"]}]},
        {"question": "Second?", "answer": [{"type": "paragraph", "text": "x"}]},
    ]
    html = TemplateService().render(
        "project_faqs.html.j2", project_name="OCEANZ & CO", faqs=faqs
    )
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html
    assert "<li>one</li>" in html and "&lt;i&gt;two&lt;/i&gt;" in html
    assert "OCEANZ &amp; CO" in html
    # One plain box per FAQ, question and answer together; no dropdowns.
    assert html.count('class="faq-item"') == 2
    assert html.count('class="faq-question"') == 2
    assert html.count('class="faq-answer"') == 2
    assert "<details" not in html and "<summary" not in html


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

OCEANZ = SimpleNamespace(
    project_id="P-OCEANZ", project_name="OCEANZ BY DANUBE", project_number=None
)
GREENZ = SimpleNamespace(
    project_id="P-GREENZ", project_name="GREENZ BY DANUBE", project_number=None
)


def make_handler(portfolio=None, fail=False):
    handler = ProjectInformationHandler(
        inventory_snapshot=SimpleNamespace(projects=[], units=[]),
        inventory_token="inv",
        access_token="tok",
    )

    async def fetch_portfolio():
        if fail:
            raise RuntimeError("OSF down")
        return portfolio or []

    async def fetch_projects(**kwargs):
        return [OCEANZ, GREENZ]

    handler.tour_connector = SimpleNamespace(fetch_portfolio=fetch_portfolio)
    handler.connector = SimpleNamespace(fetch_projects=fetch_projects)
    return handler


def faq_intent(project_name="OCEANZ BY DANUBE"):
    return SimpleNamespace(
        project_operation="faq",
        project_name=project_name,
        project_id=None,
        project_number=None,
        unit_id=None,
        unit_name=None,
        unit_number=None,
    )


PORTFOLIO = [
    {"title": "Greenz by Danube", "meta": {"aminities": []}},
    {"title": "Oceanz by Danube",
     "meta": {"danube_faqs_title_and_content": OCEANZ_FAQS}},
]


@pytest.mark.asyncio
async def test_handler_returns_all_faqs_card():
    result = await make_handler(PORTFOLIO).handle_project_faqs(
        faq_intent(), [OCEANZ, GREENZ]
    )

    assert result.has_data is True
    assert result.messages == []
    assert [b["card_type"] for b in result.html_blocks] == ["project_faqs"]
    html = result.html_blocks[0]["html"]
    for entry in OCEANZ_FAQS:
        assert entry["danube_faqs_title"].replace("'", "&#39;") in html
    assert "data-sourcepos" not in html

    ctx = result.generation_context
    assert ctx["operation"] == "faq"
    assert ctx["faq_count"] == len(OCEANZ_FAQS)
    # Only questions are passed to the LLM, never the answers.
    assert "Breathtaking" not in str(ctx)


@pytest.mark.asyncio
async def test_handler_project_without_faqs():
    result = await make_handler(PORTFOLIO).handle_project_faqs(
        faq_intent("GREENZ BY DANUBE"), [OCEANZ, GREENZ]
    )
    assert result.has_data is False
    assert result.html_blocks == []
    assert result.messages == ["No FAQs are currently available for GREENZ BY DANUBE."]


@pytest.mark.asyncio
async def test_handler_osf_failure_is_friendly():
    result = await make_handler(fail=True).handle_project_faqs(
        faq_intent(), [OCEANZ, GREENZ]
    )
    assert result.has_data is False
    assert result.messages == ["Project FAQs are temporarily unavailable. Please try again."]


@pytest.mark.asyncio
async def test_handler_unknown_project_uses_existing_resolution():
    result = await make_handler(PORTFOLIO).handle_project_faqs(
        faq_intent("NOT A PROJECT"), [OCEANZ, GREENZ]
    )
    assert result.has_data is False
    assert result.html_blocks == []
    assert result.messages      # existing resolve_project error message


@pytest.mark.asyncio
async def test_handle_dispatches_faq_operation():
    result = await make_handler(PORTFOLIO).handle(faq_intent())
    assert [b["card_type"] for b in result.html_blocks] == ["project_faqs"]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def routing(intent, **fields):
    base = dict(
        intent=intent,
        original_query="q",
        expanded_query="q",
        action="a",
        project_name=None,
        unit_number=None,
        bedrooms=None,
        currency=None,
        file_format=None,
        bank_account_types=[],
        marketing_assets=[],
        missing_fields=[],
        requires_clarification=False,
    )
    base.update(fields)
    return RoutingResult(
        language="en",
        intents=[RoutingIntent(**base)],
        requires_clarification=False,
    )


def test_schema_accepts_faq_and_existing_operations():
    for op in ["latest", "list", "details", "location_search", "tour", "amenities", "faq"]:
        assert routing("project_information", project_operation=op)


def test_validate_faq_with_project_needs_no_clarification():
    r = RouterService.validate_routing(
        routing("project_information", project_operation="faq",
                project_name="OCEANZ BY DANUBE")
    )
    assert r.intents[0].requires_clarification is False


def test_validate_faq_without_project_asks_for_project():
    r = RouterService.validate_routing(
        routing("project_information", project_operation="faq")
    )
    assert "project_identifier" in r.intents[0].missing_fields
    assert r.requires_clarification is True


@pytest.mark.parametrize("message", [
    "FAQs for Oceanz", "oceanz faq", "show frequently asked questions for Oceanz",
    "Oceanz F.A.Q.",
])
@pytest.mark.parametrize("wrong_intent", ["greeting", "about_assistant", "out_of_scope"])
def test_safety_net_converts_conversational_misroute(message, wrong_intent):
    r = RouterService.apply_faq_safety_net(
        routing(wrong_intent, project_name="OCEANZ BY DANUBE"), message
    )
    item = r.intents[0]
    assert (item.intent, item.project_operation) == ("project_information", "faq")
    assert item.requires_clarification is False


def test_safety_net_converts_details_to_faq():
    r = RouterService.apply_faq_safety_net(
        routing("project_information", project_operation="details",
                project_name="OCEANZ BY DANUBE"),
        "Oceanz FAQs",
    )
    assert r.intents[0].project_operation == "faq"


@pytest.mark.parametrize("intent,fields", [
    ("project_information", {"project_operation": "amenities"}),
    ("project_information", {"project_operation": "tour"}),
    ("project_information", {"project_operation": "latest"}),
    ("marketing", {"marketing_assets": ["other"]}),
    ("inventory", {"inventory_scope": "units", "inventory_operation": "unit_search"}),
    ("sales_offer", {}),
])
def test_safety_net_leaves_other_routes_unchanged(intent, fields):
    original = routing(intent, project_name="OCEANZ BY DANUBE", **fields)
    before = original.model_dump()
    after = RouterService.apply_faq_safety_net(original, "FAQ for Oceanz")
    assert after.model_dump() == before


@pytest.mark.parametrize("message", [
    "Hi", "Hello there", "Tell me about Oceanz", "What is the starting price in Oceanz?",
    "Show amenities in Oceanz", "Is Oceanz a good investment?",
])
def test_safety_net_ignores_messages_without_faq_keyword(message):
    original = routing("greeting")
    before = original.model_dump()
    after = RouterService.apply_faq_safety_net(original, message)
    assert after.model_dump() == before


def test_safety_net_ignores_multi_intent():
    r = routing("greeting")
    r.intents.append(routing("inventory", inventory_scope="units").intents[0])
    before = r.model_dump()
    assert RouterService.apply_faq_safety_net(r, "FAQs for Oceanz").model_dump() == before
