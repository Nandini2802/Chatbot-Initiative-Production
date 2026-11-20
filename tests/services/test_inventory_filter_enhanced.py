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


def test_general_studio_search_includes_flex_variants():
    units = [
        InventoryUnit(
            unit_name="ST-001",
            unit_type="Studio",
            bedrooms=0,
            status="Available",
        ),
        InventoryUnit(
            unit_name="ST-002",
            unit_type=(
                "Flex Studio Type - A / "
                "Convertible 1 Bedroom"
            ),
            bedrooms=1,
            status="Available",
        ),
        InventoryUnit(
            unit_name="ST-003",
            unit_type=(
                "Flex Studio Type - B / "
                "Convertible 1 Bedroom"
            ),
            bedrooms=1,
            status="Available",
        ),
        InventoryUnit(
            unit_name="BR-001",
            unit_type="1 Bedroom",
            bedrooms=1,
            status="Available",
        ),
        InventoryUnit(
            unit_name="ST-004",
            unit_type="Flex Studio Type - A",
            bedrooms=1,
            status="Sold",
        ),
    ]

    intent = make_intent(
        unit_type="studio",
        bedrooms=0,
        status="Available",
    )

    results = InventoryFilterService().filter_units(
        units, intent
    )

    assert [u.unit_name for u in results] == [
        "ST-001",
        "ST-002",
        "ST-003",
    ]


def test_specific_flex_studio_type_a():
    units = [
        InventoryUnit(
            unit_name="ST-001",
            unit_type="Studio",
            status="Available",
        ),
        InventoryUnit(
            unit_name="ST-002",
            unit_type=(
                "Flex Studio Type - A / "
                "Convertible 1 Bedroom"
            ),
            status="Available",
        ),
        InventoryUnit(
            unit_name="ST-003",
            unit_type=(
                "Flex Studio Type - B / "
                "Convertible 1 Bedroom"
            ),
            status="Available",
        ),
    ]

    intent = make_intent(
        unit_type="Flex Studio Type - A",
        status="Available",
    )

    results = InventoryFilterService().filter_units(
        units, intent
    )

    assert [u.unit_name for u in results] == [
        "ST-002"
    ]


def test_one_bedroom_search_keeps_existing_behavior():
    units = [
        InventoryUnit(
            unit_name="ST-001",
            unit_type="Studio",
            bedrooms=0,
            status="Available",
        ),
        InventoryUnit(
            unit_name="BR-001",
            unit_type="1 Bedroom",
            bedrooms=1,
            status="Available",
        ),
    ]

    intent = make_intent(
        bedrooms=1,
        status="Available",
    )

    results = InventoryFilterService().filter_units(
        units, intent
    )

    assert [u.unit_name for u in results] == [
        "BR-001"
    ]


def test_studio_search_does_not_match_non_studio_types():
    units = [
        InventoryUnit(
            unit_name="BR-001",
            unit_type="Convertible 1 Bedroom",
            status="Available",
        ),
        InventoryUnit(
            unit_name="BR-002",
            unit_type="2 Bedroom",
            status="Available",
        ),
        InventoryUnit(
            unit_name="ST-001",
            unit_type="Studio",
            status="Available",
        ),
    ]

    intent = make_intent(
        unit_type="studio",
        status="Available",
    )

    results = InventoryFilterService().filter_units(
        units, intent
    )

    assert [u.unit_name for u in results] == [
        "ST-001"
    ]
