
import pytest

from app.schemas.retrieval import InventoryUnit
from app.services.unit_comparison_resolver import (
    extract_explicit_unit_references,
    resolve_comparison_unit,
)


@pytest.fixture
def units():
    return [
        InventoryUnit(
            unit_id="U1",
            project_id="P1",
            project_name="GREENZ BY DANUBE",
            building_name="GREENZ BY DANUBE",
            unit_name="GRZ-TH-230",
            unit_code="230",
        ),
        InventoryUnit(
            unit_id="U2",
            project_id="P1",
            project_name="GREENZ BY DANUBE",
            building_name="GREENZ BY DANUBE",
            unit_name="GRZ-TH-236",
            unit_code="236",
        ),
        InventoryUnit(
            unit_id="U3",
            project_id="P2",
            project_name="ASPIRZ BY DANUBE",
            building_name="ASPIRZ BY DANUBE",
            unit_name="ASPZ-F02-201",
            unit_code="201",
        ),
        InventoryUnit(
            unit_id="U4",
            project_id="P2",
            project_name="ASPIRZ BY DANUBE",
            building_name="ASPIRZ BY DANUBE",
            unit_name="ASPZ-F12-1201",
            unit_code="1201",
        ),
    ]


@pytest.mark.parametrize(
    "identifier,expected",
    [
        ("Greenz 230", "GRZ-TH-230"),
        ("greenz 230", "GRZ-TH-230"),
        ("GRZ-TH-230", "GRZ-TH-230"),
        ("GRZ TH 230", "GRZ-TH-230"),
        ("Aspirz 201", "ASPZ-F02-201"),
        ("aspirz 1201", "ASPZ-F12-1201"),
        ("ASPZ-F02-201", "ASPZ-F02-201"),
        ("Greenz 236", "GRZ-TH-236"),
    ],
)
def test_unit_resolution(units, identifier, expected):
    unit, status = resolve_comparison_unit(
        identifier,
        units,
    )

    assert status == "matched"
    assert unit.unit_name == expected


def test_router_format_with_short_numbers(units):
    first, status1 = resolve_comparison_unit(
        "230",
        units,
    )
    second, status2 = resolve_comparison_unit(
        "201",
        units,
        project_hint="ASPIRZ BY DANUBE",
    )

    assert status1 == "matched"
    assert status2 == "matched"

    assert first.unit_name == "GRZ-TH-230"
    assert second.unit_name == "ASPZ-F02-201"


def test_exact_code_not_partial_match(units):
    unit, status = resolve_comparison_unit(
        "Aspirz 201",
        units,
    )

    assert status == "matched"
    assert unit.unit_name == "ASPZ-F02-201"
    assert unit.unit_name != "ASPZ-F12-1201"


def test_explicit_project_pairs(units):
    result = extract_explicit_unit_references(
        "compare greenz 230 vs aspirz 201",
        units,
    )

    assert result == [
        "greenz 230",
        "aspirz 201",
    ]


def test_same_project_comparison(units):
    result = extract_explicit_unit_references(
        "compare greenz 230 vs greenz 236",
        units,
    )

    assert result == [
        "greenz 230",
        "greenz 236",
    ]


def test_duplicate_unit_code_requires_clarification(units):
    units.append(
        InventoryUnit(
            unit_id="U5",
            project_id="P2",
            project_name="ASPIRZ BY DANUBE",
            unit_name="ASPZ-F03-201",
            unit_code="201",
        )
    )

    unit, status = resolve_comparison_unit(
        "Aspirz 201",
        units,
    )

    assert unit is None
    assert status == "ambiguous"


def test_identical_codes_across_projects(units):
    units.append(
        InventoryUnit(
            unit_id="U6",
            project_id="P3",
            project_name="OTHER PROJECT",
            unit_name="OTH-F01-230",
            unit_code="230",
        )
    )

    unit, status = resolve_comparison_unit(
        "230",
        units,
    )

    assert unit is None
    assert status == "ambiguous"

    unit, status = resolve_comparison_unit(
        "Greenz 230",
        units,
    )

    assert status == "matched"
    assert unit.unit_name == "GRZ-TH-230"
