"""
Sales offer: project-only requests show the unit list (no auto-pick),
and typed unit replies are matched tolerantly.

Matching order (resolve_sales_offer_selection):
  1. Existing rules (exact name, ordinals, "unit 1234", partial) - unchanged
  2. Formatting-only differences (case/separators/leading zeros) - selected directly
  3. Unit inside a short sentence ("the 188 one")
  4. One-edit typo -> one match: "Are you referring to ...?"; 2-5: "Did you mean ...?"
  5. Bare number -> position in the list ("2")
Anything else keeps today's behaviour.
"""
import json
from types import SimpleNamespace

import pytest

import app.handlers.sales_offer_handler as soh
from app.services.sales_offer_followup import resolve_sales_offer_selection
from app.services.sales_offer_resolver import SalesOfferResolutionError

NAMES = [
    "GRZ-TH-170", "GRZ-TH-171", "GRZ-TH-180", "GRZ-TH-187",
    "GRZ-TH-188", "GRZ-TH-190", "GRZ-V-18", "GRZ-TH-808",
]


class Unit(SimpleNamespace):
    """Unit record; attributes not set default to None."""

    def __getattr__(self, name):
        return None


UNITS = [
    Unit(unit_id=f"ID-{n}", unit_name=n, unit_code=n,
         project_name="GREENZ BY DANUBE", project_id="P-GRZ")
    for n in NAMES
]
SNAPSHOT = SimpleNamespace(units=UNITS, projects=[])
PENDING = {
    "stage": "unit_selection",
    "candidate_unit_ids": [u.unit_id for u in UNITS],
    "displayed_unit_ids": [u.unit_id for u in UNITS],
    "currency": "AED",
}


def select(message):
    return resolve_sales_offer_selection(message, dict(PENDING), SNAPSHOT)


# ---------------------------------------------------------------------------
# Matching matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message,unit,confirm", [
    # --- worked before, unchanged ---
    ("GRZ-TH-188", "GRZ-TH-188", False),
    ("grz-th-188", "GRZ-TH-188", False),
    ("I want GRZ-TH-188", "GRZ-TH-188", False),
    ("188", "GRZ-TH-188", True),
    ("unit 188", "GRZ-TH-188", True),
    ("TH-188", "GRZ-TH-188", True),
    ("th 188", "GRZ-TH-188", True),
    ("808", "GRZ-TH-808", True),
    ("v 18", "GRZ-V-18", True),
    ("18", "GRZ-V-18", True),          # unit number wins over "18th in list"
    ("second one", "GRZ-TH-171", False),
    ("option 2", "GRZ-TH-171", False),
    # --- formatting only: now selected without confirmation ---
    ("grz th 188", "GRZ-TH-188", False),
    ("GRZ_TH_188", "GRZ-TH-188", False),
    ("GRZ-TH188", "GRZ-TH-188", False),
    ("grzth188", "GRZ-TH-188", False),
    ("grz-th-0188", "GRZ-TH-188", False),
    # --- unit inside a short sentence ---
    ("the 188 one", "GRZ-TH-188", True),
    ("I want grz th 188 please", "GRZ-TH-188", False),
    # --- one typo, single close unit: confirm ---
    ("GRZ-TJ-188", "GRZ-TH-188", True),
    ("GRX-TH-188", "GRZ-TH-188", True),
    ("GZR-TH-188", "GRZ-TH-188", True),
    ("GRZ-TH-1888", "GRZ-TH-188", True),
    ("grz tj 188", "GRZ-TH-188", True),
    # --- bare number: position in list ---
    ("2", "GRZ-TH-171", False),
])
def test_selection(message, unit, confirm):
    result = select(message)
    assert result is not None, message
    assert (result[0].unit_name, result[1]) == (unit, confirm)


@pytest.mark.parametrize("message,expected_options", [
    ("GRZ-TH-818", "GRZ-TH-188 or GRZ-TH-808"),
    ("GRZ-TH-18", "GRZ-TH-180, GRZ-TH-187 or GRZ-TH-188"),
])
def test_several_close_units_are_offered(message, expected_options):
    with pytest.raises(SalesOfferResolutionError) as err:
        select(message)
    assert str(err.value) == (
        f"I found close matches: {expected_options}. Which unit did you mean?"
    )


@pytest.mark.parametrize("message", ["GRZ-TH-881", "GXR-TJ-881", "GRZ-TH-999"])
def test_too_far_keeps_existing_not_found_error(message):
    with pytest.raises(SalesOfferResolutionError) as err:
        select(message)
    assert "couldn't find that unit" in str(err.value)


@pytest.mark.parametrize("message", [
    "give me unit under 2 million",
    "units under 200",
    "for this GRZ-TH-999",
    "hello",
    "99",                      # beyond the list
    "what is the price",
])
def test_not_a_selection_stays_none(message):
    assert select(message) is None


def test_suggestions_only_from_the_offered_list():
    # GRZ-TH-189 exists in inventory but was not in this user's list.
    other = Unit(unit_id="ID-GRZ-TH-189", unit_name="GRZ-TH-189", unit_code="GRZ-TH-189")
    snapshot = SimpleNamespace(units=UNITS + [other], projects=[])
    pending = dict(PENDING)
    result = resolve_sales_offer_selection("GRZ-TH-1889", pending, snapshot)
    assert result[0].unit_name == "GRZ-TH-188"     # never GRZ-TH-189


# ---------------------------------------------------------------------------
# Handler flow
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


def handler(redis, message, monkeypatch):
    monkeypatch.setattr(soh, "find_project_units", lambda intent, snapshot: UNITS)
    return soh.SalesOfferHandler(
        inventory_snapshot=SNAPSHOT, redis_client=redis, access_token="tok",
        user_id="u", session_id="s", message=message, db_session=None,
    )


def state(redis):
    raw = next(iter(redis.store.values()), None)
    return json.loads(raw) if raw else None


INTENT = SimpleNamespace(
    project_name="GREENZ BY DANUBE", project_id=None, project_number=None,
    unit_id=None, unit_name=None, unit_number=None, currency=None,
)


@pytest.mark.asyncio
async def test_project_only_shows_unit_list_not_auto_pick(monkeypatch):
    redis = FakeRedis()
    result = await handler(redis, "Sales offer for greenz", monkeypatch).handle(INTENT)

    assert "Please specify the unit" in result.messages[0]
    assert [b["card_type"] for b in result.html_blocks] == ["inventory_listing"]
    assert "has been selected" not in " ".join(result.messages)
    assert state(redis)["stage"] == "unit_selection"


@pytest.mark.asyncio
async def test_exact_unit_goes_straight_to_currency(monkeypatch):
    redis = FakeRedis()
    await handler(redis, "Sales offer for greenz", monkeypatch).handle(INTENT)
    result = await handler(redis, "GRZ-TH-188", monkeypatch).handle(INTENT)

    assert "Unit GRZ-TH-188 in GREENZ BY DANUBE has been selected" in result.messages[0]
    assert state(redis)["stage"] == "currency_confirmation"


@pytest.mark.asyncio
async def test_typo_confirm_yes_continues(monkeypatch):
    redis = FakeRedis()
    await handler(redis, "Sales offer for greenz", monkeypatch).handle(INTENT)

    result = await handler(redis, "GRZ-TJ-188", monkeypatch).handle(INTENT)
    assert result.messages[0].startswith("Are you referring to unit GRZ-TH-188")
    assert state(redis)["stage"] == "unit_confirmation"

    result = await handler(redis, "yes", monkeypatch).handle(INTENT)
    assert "Unit GRZ-TH-188" in result.messages[0]
    assert state(redis)["stage"] == "currency_confirmation"


@pytest.mark.asyncio
async def test_typo_confirm_no_returns_to_list(monkeypatch):
    redis = FakeRedis()
    await handler(redis, "Sales offer for greenz", monkeypatch).handle(INTENT)
    await handler(redis, "GRZ-TJ-188", monkeypatch).handle(INTENT)

    result = await handler(redis, "no", monkeypatch).handle(INTENT)
    assert result.messages[0].startswith("No problem. Please type the unit name")
    s = state(redis)
    assert s["stage"] == "unit_selection"
    assert s["candidate_unit_ids"] == PENDING["candidate_unit_ids"]

    # ...and the user can pick again from the same list.
    result = await handler(redis, "second one", monkeypatch).handle(INTENT)
    assert "Unit GRZ-TH-171" in result.messages[0]


@pytest.mark.asyncio
async def test_close_matches_keep_list_open(monkeypatch):
    redis = FakeRedis()
    await handler(redis, "Sales offer for greenz", monkeypatch).handle(INTENT)

    result = await handler(redis, "GRZ-TH-18", monkeypatch).handle(INTENT)
    assert result.messages[0] == (
        "I found close matches: GRZ-TH-180, GRZ-TH-187 or GRZ-TH-188. "
        "Which unit did you mean?"
    )
    assert state(redis)["stage"] == "unit_selection"


@pytest.mark.asyncio
async def test_unrecognised_reply_keeps_existing_message(monkeypatch):
    redis = FakeRedis()
    await handler(redis, "Sales offer for greenz", monkeypatch).handle(INTENT)

    result = await handler(redis, "hello", monkeypatch).handle(INTENT)
    assert result.messages[0].startswith("Please select a unit from the listing.")
    assert state(redis)["stage"] == "unit_selection"


@pytest.mark.asyncio
async def test_no_without_list_keeps_old_behaviour(monkeypatch):
    # A confirmation that did not come from the list (e.g. a fuzzy unit in
    # the first request) still clears the flow as before.
    redis = FakeRedis()
    h = handler(redis, "no", monkeypatch)
    await h.save({"stage": "unit_confirmation", "unit_id": "ID-GRZ-TH-188",
                  "unit_name": "GRZ-TH-188", "project_name": "GREENZ BY DANUBE",
                  "currency": "AED"})
    result = await h.handle(INTENT)
    assert result.messages[0].startswith("Please specify the unit")
    assert state(redis) is None
