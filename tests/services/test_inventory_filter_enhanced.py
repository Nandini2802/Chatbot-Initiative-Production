from app.schemas.retrieval import InventoryUnit
from app.schemas.routing import RoutingIntent
from app.services.inventory_filter_service import (
    InventoryFilterService,
)


def make_intent(**overrides):
    data = {
        "intent": "inventory",
        "original_query": "Search inventory",
        "expanded_query": "Search inventory",
        "action": "search",
        "project_name": None,
        "unit_number": None,
        "bedrooms": None,
        "currency": None,
        "file_format": None,
        "bank_account_types": [],
        "marketing_assets": [],
        "missing_fields": [],
        "requires_clarification": False,
        "inventory_scope": "units",
        "inventory_operation": "unit_search",
    }

    data.update(overrides)
    return RoutingIntent(**data)


def sample_units():
    return [
        InventoryUnit(
            unit_name="UNIT-001",
            project_name="ASPIRZ BY DANUBE",
            project_location="DUBAI SPORTS CITY",
            category="Residential",
            unit_type="1 Bedroom",
            bedrooms=None,
            view="Canal View & City View",
            price=1800000,
            currency="AED",
            status="Available",
        ),
        InventoryUnit(
            unit_name="UNIT-002",
            project_name="ASPIRZ BY DANUBE",
            project_location="DUBAI SPORTS CITY",
            category="Commercial",
            typology="Office",
            unit_type="1 Bedroom",
            bedrooms=None,
            view="Cricket Stadium View",
            price=2770002,
            currency="AED",
            status="Available",
        ),
        InventoryUnit(
            unit_name="UNIT-003",
            project_name="ANOTHER PROJECT",
            project_location="DOWNTOWN",
            category="Residential",
            unit_type="2 BHK Type - G",
            view="Sea View",
            price=3500000,
            currency="AED",
            status="Available",
        ),
    ]


def test_city_view_under_two_million():
    intent = make_intent(
        view="city view",
        max_price=2000000,
        status="Available",
        currency="AED",
    )

    result = InventoryFilterService().filter_units(
        sample_units(), intent
    )

    assert [u.unit_name for u in result] == ["UNIT-001"]


def test_sports_city_between_two_and_three_million():
    intent = make_intent(
        project_location="Sports City",
        min_price=2000000,
        max_price=3000000,
        status="Available",
        currency="AED",
    )

    result = InventoryFilterService().filter_units(
        sample_units(), intent
    )

    assert [u.unit_name for u in result] == ["UNIT-002"]


def test_stadium_view():
    intent = make_intent(
        view="Cricket Stadium View",
        status="Available",
    )

    result = InventoryFilterService().filter_units(
        sample_units(), intent
    )

    assert [u.unit_name for u in result] == ["UNIT-002"]


def test_bedroom_fallback():
    intent = make_intent(
        bedrooms=1,
        category="Residential",
    )

    result = InventoryFilterService().filter_units(
        sample_units(), intent
    )

    assert [u.unit_name for u in result] == ["UNIT-001"]


def test_no_match_does_not_return_everything():
    intent = make_intent(
        view="City View",
        max_price=1000000,
        status="Available",
    )

    result = InventoryFilterService().filter_units(
        sample_units(), intent
    )

    assert result == []