
from types import SimpleNamespace

import pytest

from app.services.sales_offer_followup import (
    resolve_sales_offer_selection,
)


def make_unit(unit_id):
    return SimpleNamespace(
        unit_id=unit_id,
        unit_name=unit_id,
        unit_code=unit_id,
    )


@pytest.fixture
def snapshot():
    return SimpleNamespace(
        units=[
            make_unit("GRZ-TH-170"),
            make_unit("GRZ-TH-171"),
            make_unit("GRZ-TH-172"),
        ]
    )


@pytest.fixture
def pending():
    return {
        "stage": "unit_selection",
        "candidate_unit_ids": [
            "GRZ-TH-170",
            "GRZ-TH-171",
            "GRZ-TH-172",
        ],
        "displayed_unit_ids": [
            "GRZ-TH-170",
            "GRZ-TH-171",
            "GRZ-TH-172",
        ],
        "currency": "AED",
    }


@pytest.mark.parametrize(
    "message,expected",
    [
        ("first one", "GRZ-TH-170"),
        ("second one", "GRZ-TH-171"),
        ("third one", "GRZ-TH-172"),
        ("for this GRZ-TH-171", "GRZ-TH-171"),
        ("GRZ-TH-172", "GRZ-TH-172"),
        ("for this unit GRZ-TH-170", "GRZ-TH-170"),
        ("select GRZ-TH-171", "GRZ-TH-171"),
    ],
)
def test_sales_offer_selection(
    message,
    expected,
    pending,
    snapshot,
):
    result = resolve_sales_offer_selection(
        message=message,
        pending=pending,
        snapshot=snapshot,
    )

    assert result is not None

    unit, needs_confirmation = result

    assert unit.unit_id == expected
    assert needs_confirmation is False


def test_inventory_switch_not_a_selection(
    pending,
    snapshot,
):
    result = resolve_sales_offer_selection(
        message="give me unit under 2 million",
        pending=pending,
        snapshot=snapshot,
    )

    assert result is None


def test_unknown_unit_not_selected(
    pending,
    snapshot,
):
    result = resolve_sales_offer_selection(
        message="for this GRZ-TH-999",
        pending=pending,
        snapshot=snapshot,
    )

    assert result is None
