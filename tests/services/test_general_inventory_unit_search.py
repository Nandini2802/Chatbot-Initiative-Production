import pytest

from app.schemas.routing import RoutingIntent
from app.services.streaming_service import (
    is_general_inventory_unit_search,
)


def build_intent(**overrides):

    data = {
        "intent": "inventory",
        "inventory_operation": "unit_search",
        "inventory_scope": "units",
        "project_reference_source": "none",
        "project_name": None,
        "project_family": None,
        "explicit_project_reference": None,
        "project_id": None,
        "project_number": None,
        "unit_id": None,
        "unit_name": None,
        "unit_number": None,
        "original_query": "Show all units",
        "expanded_query": "Show all units",
        "action": "search",
        "bedrooms": None,
        "currency": None,
        "file_format": None,
        "bank_account_types": [],
        "marketing_assets": [],
        "missing_fields": [],
        "requires_clarification": False,
    }

    data.update(overrides)

    return RoutingIntent(**data)


@pytest.mark.parametrize(
    "message",
    [
        "Show all units with skyline view",
        "Show all units with sea view",
        "Show units with private pool",
        "Show apartments below 2 million",
        "Show units above the 20th floor",
        "Show 2 bedroom apartments",
        "Show duplex apartments",
        "Show units with panoramic views",
        "Show units near the metro",
    ],
)
def test_general_inventory_search(message):

    intent = build_intent(
        original_query=message,
        expanded_query=message,
    )

    assert is_general_inventory_unit_search(intent) is True


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "project_name": "VIEWZ 1 BY DANUBE",
        },
        {
            "project_family": "VIEWZ",
        },
        {
            "explicit_project_reference": "VIEWZ",
        },
        {
            "project_reference_source": "explicit",
        },
        {
            "project_reference_source": "context",
        },
        {
            "project_reference_source": "uncertain",
        },
        {
            "project_id": "project123",
        },
        {
            "project_number": "123",
        },
        {
            "unit_id": "unit123",
        },
        {
            "unit_name": "UNIT-808",
        },
        {
            "unit_number": "808",
        },
        {
            "inventory_operation": "unit_comparison",
        },
        {
            "inventory_operation": "project_comparison",
        },
        {
            "inventory_operation": "unit_details",
        },
        {
            "inventory_operation": "payment_plan",
        },
        {
            "inventory_scope": "projects",
        },
        {
            "intent": "marketing",
        },
        {
            "intent": "bank_details",
        },
        {
            "intent": "download_availability",
        },
    ],
)
def test_existing_resolution_is_preserved(overrides):

    intent = build_intent(**overrides)

    assert is_general_inventory_unit_search(intent) is False


def test_missing_inventory_scope():

    intent = build_intent(
        inventory_scope=None,
    )

    assert is_general_inventory_unit_search(intent) is True


def test_explicit_project_with_view_filter():

    intent = build_intent(
        original_query="Show skyline view units in VIEWZ 2",
        project_name="VIEWZ 2 BY DANUBE",
        explicit_project_reference="VIEWZ 2",
        project_reference_source="explicit",
        view="skyline",
    )

    assert is_general_inventory_unit_search(intent) is False


def test_contextual_followup():

    intent = build_intent(
        original_query="What about skyline view?",
        project_name="VIEWZ 1 BY DANUBE",
        project_reference_source="context",
        view="skyline",
    )

    assert is_general_inventory_unit_search(intent) is False
