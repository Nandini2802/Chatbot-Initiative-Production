"""
Reproduction: submitting the standalone payment-plan selection card.

The card (payment_plan_selection.html.j2) posts
`selected_payment_plan_names=[<plan name>]`. For a plain
"give me payment plan for <project>" request the pending selection lives
in Redis (payment_plan_context_service), NOT in SalesOfferState.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import streaming_service as ss
from app.services.payment_plan_context_service import (
    save_pending_payment_selection,
)

PLANS = [
    {"Id": "p1", "Name": "GREENZ - 30/70 ON-HANDOVER PAYMENT PLAN - NOV 2026"},
    {"Id": "p2", "Name": "GREENZ - 60/40 ON-HANDOVER PAYMENT PLAN - NOV 2026"},
]


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def harness(monkeypatch):
    redis = FakeRedis()
    clients = SimpleNamespace(redis=redis, foundry_openai=object())
    snapshot = SimpleNamespace(projects=[], units=[])

    monkeypatch.setattr(ss, "load_chat_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        ss, "load_session_project_context", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        ss, "load_previous_inventory_context", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(ss, "load_application_secrets", AsyncMock(return_value={}))
    monkeypatch.setattr(ss, "SalesforceClient", lambda **kw: object())
    monkeypatch.setattr(
        ss,
        "InventoryConnector",
        lambda **kw: SimpleNamespace(
            fetch_inventory=AsyncMock(return_value=snapshot)
        ),
    )
    monkeypatch.setattr(
        ss,
        "get_inventory_token_service",
        lambda **kw: SimpleNamespace(get_token=AsyncMock(return_value="tok")),
    )
    monkeypatch.setattr(
        ss,
        "ProjectCatalogService",
        lambda **kw: SimpleNamespace(
            get_project_names=AsyncMock(return_value=["Greenz"])
        ),
    )
    monkeypatch.setattr(ss, "resolve_authorized_units", lambda *a, **k: [])
    monkeypatch.setattr(
        ss.InventoryCatalogService,
        "build",
        staticmethod(
            lambda s: SimpleNamespace(active_projects=[], unit_projects=[])
        ),
    )

    # The router is an LLM call; return "no intents" so the flow proceeds
    # to the selected_payment_plan_names guard.
    class FakeRouter:
        def __init__(self, **kw):
            pass

        async def classify(self, **kw):
            return SimpleNamespace(intents=[])

    monkeypatch.setattr(ss, "RouterService", FakeRouter)
    monkeypatch.setattr(
        ss,
        "get_settings",
        lambda: SimpleNamespace(foundry_openai_model="m"),
    )
    monkeypatch.setattr(ss, "persist_completed_chat", AsyncMock())
    monkeypatch.setattr(ss, "audit_event", lambda *a, **k: None)
    return clients


async def _run(clients, **kwargs):
    events = []
    async for ev in ss._stream_chat_response_impl(
        message="Selected payment plans",
        session_id=uuid.uuid4(),
        correlation_id="c",
        user_id="u",
        role="customer",
        source="web_app",
        employee_type="",
        clients=clients,
        access_token="t",
        walkthrough_engine=SimpleNamespace(guides={}),
        key_features="",
        **kwargs,
    ):
        events.append(ev)
    return events


llm_calls = []


def fake_llm(action, index=None):
    """LLM used by interpret_payment_selection for the card message."""
    content = json.dumps({"action": action, "selected_index": index})

    async def create(**kw):
        llm_calls.append(kw)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "llm_action,llm_index",
    [("select", 1), ("new_request", None), ("clarify", None)],
)
async def test_standalone_payment_plan_card_submit(
    harness, monkeypatch, llm_action, llm_index
):
    """
    Card submit after a plain 'payment plan for <project>' request.

    The card sends selected_payment_plan=<exact plan name>. Whatever the LLM
    would have answered, the server must match the name exactly against the
    pending Redis list and show that plan without asking the LLM.
    """
    clients = harness
    llm_calls.clear()
    clients.foundry_openai = fake_llm(llm_action, llm_index)
    monkeypatch.setattr(ss, "PaymentPlanHandler", FakePaymentHandler)
    FakePaymentHandler.calls.clear()
    session_id = uuid.uuid4()

    await save_pending_payment_selection(
        redis_client=clients.redis,
        user_id="u",
        session_id=str(session_id),
        unit_id="GRZ-TH-188",
        unit_name="GRZ-TH-188",
        plans=PLANS,
    )

    events = []
    async for ev in ss._stream_chat_response_impl(
        message="Selected payment plans: " + PLANS[0]["Name"],
        session_id=session_id,
        correlation_id="c",
        user_id="u",
        role="customer",
        source="web_app",
        employee_type="",
        clients=clients,
        access_token="t",
        walkthrough_engine=SimpleNamespace(guides={}),
        key_features="",
        # What payment_plan_selection.html.j2 now posts:
        selected_payment_plan=PLANS[0]["Name"],
    ):
        events.append(ev)

    joined = "".join(events)
    print(joined)
    assert "event: error" not in joined, joined
    assert "requires_clarification" not in joined, joined
    # Exact-name path: the LLM interpreter must never be consulted.
    assert llm_calls == [], llm_calls
    assert FakePaymentHandler.calls == ["p1"]


# ---------------------------------------------------------------------------
# Frontend payload shape (confirmed): singular `selected_payment_plan`.
#   {"message": "Selected payment plan",
#    "selected_payment_plan": "<exact plan name>", ...}
# ---------------------------------------------------------------------------

DOTD = "GREENZ - DEAL OF THE DECADE (0.5%) POST HANDOVER - 10% UPFRONT"


class FakePaymentHandler:
    calls = []

    def __init__(self, **kw):
        pass

    async def handle(self, intent, selected_plan_id=None):
        FakePaymentHandler.calls.append(selected_plan_id)
        return SimpleNamespace(
            html_blocks=[{"card_type": "payment_plan", "html": "<div/>"}],
            files=[],
            messages=[],
            has_data=True,
        )


async def _submit_singular(clients, session_id, plan_name):
    events = []
    async for ev in ss._stream_chat_response_impl(
        message="Selected payment plan",
        session_id=session_id,
        correlation_id="c",
        user_id="u",
        role="Agency Admin",
        source="mobile_app",
        employee_type="",
        clients=clients,
        access_token="t",
        walkthrough_engine=SimpleNamespace(guides={}),
        key_features="",
        selected_payment_plan=plan_name,
    ):
        events.append(ev)
    return "".join(events)


@pytest.mark.asyncio
async def test_frontend_payload_with_pending_selection(harness, monkeypatch):
    """Pending list in Redis + exact plan name -> plan is shown."""
    clients = harness
    monkeypatch.setattr(ss, "PaymentPlanHandler", FakePaymentHandler)
    FakePaymentHandler.calls.clear()
    session_id = uuid.uuid4()

    await save_pending_payment_selection(
        redis_client=clients.redis,
        user_id="u",
        session_id=str(session_id),
        unit_id="GRZ-TH-188",
        unit_name="GRZ-TH-188",
        plans=PLANS + [{"Id": "p9", "Name": DOTD}],
    )

    joined = await _submit_singular(clients, session_id, DOTD)
    print(joined)
    assert "event: error" not in joined, joined
    assert FakePaymentHandler.calls == ["p9"]


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap: expired/missing pending selection still raises "
        "'Payment-plan selection is not active' -> generic error. "
        "Should return a friendly 'selection expired' message."
    ),
)
async def test_frontend_payload_without_pending_selection(harness, monkeypatch):
    """
    No pending list in Redis (expired after 30 min, already used once,
    cleared, or different session) -> server raises
    'Payment-plan selection is not active' -> generic error to the user.
    """
    clients = harness
    monkeypatch.setattr(ss, "PaymentPlanHandler", FakePaymentHandler)
    joined = await _submit_singular(clients, uuid.uuid4(), DOTD)
    print(joined)
    assert "event: error" not in joined, joined


# ---------------------------------------------------------------------------
# Template content: both cards send the picked names in the chat message.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "template,context",
    [
        ("payment_plan_selection.html.j2", {"plans": [{"name": "Plan A"}]}),
        (
            "sales_offer_plans.html.j2",
            {"plans": [{"payPlanName": "Plan A", "id": "1"}]},
        ),
    ],
)
def test_card_templates_render_new_message(template, context):
    from app.services.template_service import TemplateService

    html = TemplateService().render(template, **context)
    assert "message: 'Selected payment plans: ' + picks.join(', ')" in html
    if template == "payment_plan_selection.html.j2":
        # Single-select card -> singular field read by the payment-plan flow.
        assert "extra: { selected_payment_plan: picks[0] }" in html
        assert "selected_payment_plan_names" not in html
    else:
        # Multi-select sales-offer card keeps the list field.
        assert "extra: { selected_payment_plan_names: picks }" in html
