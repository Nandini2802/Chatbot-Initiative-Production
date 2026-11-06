
from types import SimpleNamespace

import pytest

from app.services.sales_offer_resolver import (
    find_unit,
    SalesOfferResolutionError,
    extract_explicit_sales_offer_unit_reference,
)


@pytest.fixture
def snapshot():
    return SimpleNamespace(
        projects=[
            SimpleNamespace(
                project_id="PROJECT_ASPIRZ",
                project_name="ASPIRZ BY DANUBE",
                project_number="3838",
            )
        ],
        units=[
            SimpleNamespace(
                unit_id="UNIT_ASPIRZ_11013",
                unit_name="ASPZ-F02-11013",
                unit_code="ASPZ-F02-11013",
                project_id="PROJECT_ASPIRZ",
                project_name="ASPIRZ BY DANUBE",
            )
        ],
    )


@pytest.mark.parametrize(
    "query,needs_confirmation",
    [
        (
            "generate sales offer for ASPZ-F02-11013",
            False,
        ),
        (
            "sales offer for Aspz-F02-11013",
            False,
        ),
        (
            "sales offer for ASPZF0211013",
            True,
        ),
        (
            "sales offer for ASPZ F02 11013",
            True,
        ),
        (
            "generate sales offer for F02-11013",
            True,
        ),
        (
            "sales offer for f0211013",
            True,
        ),
        (
            "sales offer for unit 11013",
            True,
        ),
        (
            "sales offer for Aspirz 11013",
            True,
        ),
    ],
)
def test_all_eight_sales_offer_variations(
    query,
    needs_confirmation,
    snapshot,
):
    requested = (
        extract_explicit_sales_offer_unit_reference(
            query,
            snapshot,
        )
    )

    assert requested is not None

    unit, confirmation = find_unit(
        requested,
        snapshot,
    )

    assert unit.unit_name == "ASPZ-F02-11013"
    assert confirmation is needs_confirmation


def test_project_only_request_is_preserved(snapshot):
    requested = (
        extract_explicit_sales_offer_unit_reference(
            "sales offer for Aspirz",
            snapshot,
        )
    )

    assert requested is None


def test_project_number_not_treated_as_unit(snapshot):
    requested = (
        extract_explicit_sales_offer_unit_reference(
            "sales offer for project number 3838",
            snapshot,
        )
    )

    assert requested is None


def test_ambiguous_numeric_unit_reference(snapshot):
    snapshot.units.append(
        SimpleNamespace(
            unit_id="UNIT_ASPIRZ_OTHER",
            unit_name="ASPZ-F03-11013",
            unit_code="ASPZ-F03-11013",
            project_id="PROJECT_ASPIRZ",
            project_name="ASPIRZ BY DANUBE",
        )
    )

    with pytest.raises(SalesOfferResolutionError):
        find_unit(
            "11013",
            snapshot,
        )


def test_floor_and_number_resolves_uniquely(snapshot):
    snapshot.units.append(
        SimpleNamespace(
            unit_id="UNIT_ASPIRZ_OTHER",
            unit_name="ASPZ-F03-11013",
            unit_code="ASPZ-F03-11013",
            project_id="PROJECT_ASPIRZ",
            project_name="ASPIRZ BY DANUBE",
        )
    )

    unit, confirmation = find_unit(
        "F02-11013",
        snapshot,
    )

    assert unit.unit_name == "ASPZ-F02-11013"
    assert confirmation is True


def test_unit_outside_allowed_scope_is_rejected(snapshot):
    with pytest.raises(SalesOfferResolutionError):
        find_unit(
            "ASPZ-F02-11013",
            snapshot,
            allowed_unit_ids=[],
        )


def test_unknown_unit_is_rejected(snapshot):
    with pytest.raises(SalesOfferResolutionError):
        find_unit(
            "F02-99999",
            snapshot,
        )


def test_project_and_unit_combination(snapshot):
    unit, confirmation = find_unit(
        "Aspirz 11013",
        snapshot,
    )

    assert unit.unit_name == "ASPZ-F02-11013"
    assert confirmation is True
