
from types import SimpleNamespace

from app.services.shared_unit_resolver import (
    resolve_units,
    select_candidate,
    get_unit_references,
    apply_selected_unit,
)


def make_unit(name, code, project, uid):
    return SimpleNamespace(
        unit_id=uid,
        unit_name=name,
        unit_code=code,
        project_name=project,
        project_code=None,
        building_name=None,
        building_code=None,
    )


UNITS = [
    make_unit(
        "SRNZ-A-F01-101",
        "101",
        "SERENZ BY DANUBE",
        "id-srnz-a-101",
    ),
    make_unit(
        "SRNZ-B-F01-101",
        "101",
        "SERENZ BY DANUBE",
        "id-srnz-b-101",
    ),
    make_unit(
        "SRNZ-B-F11-1114",
        "1114",
        "SERENZ BY DANUBE",
        "id-srnz-1114",
    ),
    make_unit(
        "ETZ-3-A-F37-3705",
        "3705",
        "ELITZ 3",
        "id-etz-3705",
    ),
    make_unit(
        "SPLZ-B-F08-810",
        "810",
        "SPARKLZ",
        "id-splz-810",
    ),
    make_unit(
        "SPLZ-B-GF-Retail 01",
        "01",
        "SPARKLZ",
        "id-splz-retail-01",
    ),
]


def test_serenz_101_is_ambiguous():
    result = resolve_units(
        "srnz 101",
        UNITS,
    )

    assert result.status == "ambiguous"
    assert len(result.units) == 2


def test_serenz_1114_unique():
    result = resolve_units(
        "srnz 1114",
        UNITS,
    )

    assert result.status == "matched"
    assert result.units[0].unit_name == (
        "SRNZ-B-F11-1114"
    )


def test_exact_full_unit():
    result = resolve_units(
        "SRNZ-B-F01-101",
        UNITS,
    )

    assert result.status == "matched"
    assert result.units[0].unit_id == (
        "id-srnz-b-101"
    )


def test_tower_b_selection():
    result = resolve_units(
        "srnz 101",
        UNITS,
    )

    chosen = select_candidate(
        "Tower B",
        result.units,
    )

    assert chosen.status == "matched"
    assert chosen.units[0].unit_name == (
        "SRNZ-B-F01-101"
    )


def test_second_option():
    result = resolve_units(
        "srnz 101",
        UNITS,
    )

    chosen = select_candidate(
        "second one",
        result.units,
    )

    assert chosen.status == "matched"
    assert chosen.units[0].unit_name == (
        "SRNZ-B-F01-101"
    )


def test_no_partial_number_collision():
    result = resolve_units(
        "srnz 114",
        UNITS,
    )

    assert result.status == "not_found"


def test_elitz_full_name():
    result = resolve_units(
        "ETZ-3-A-F37-3705",
        UNITS,
    )

    assert result.status == "matched"


def test_sparklz_retail():
    result = resolve_units(
        "sparklz retail 01",
        UNITS,
    )

    assert result.status == "matched"
    assert result.units[0].unit_name == (
        "SPLZ-B-GF-Retail 01"
    )


def test_comparison_slots_preserved():
    intent = SimpleNamespace(
        intent="inventory",
        inventory_operation="unit_comparison",
        compare_unit_numbers=[
            "srnz 101",
            "sparklz 810",
        ],
        project_name=None,
        missing_fields=[],
        requires_clarification=False,
    )

    first = resolve_units(
        intent.compare_unit_numbers[0],
        UNITS,
    )

    assert first.status == "ambiguous"

    chosen = select_candidate(
        "Tower B",
        first.units,
    )

    apply_selected_unit(
        intent,
        chosen.units[0],
        slot_index=0,
    )

    assert intent.compare_unit_numbers == [
        "SRNZ-B-F01-101",
        "sparklz 810",
    ]


def test_payment_plan_receives_selected_id():
    intent = SimpleNamespace(
        intent="inventory",
        inventory_operation="payment_plan",
        unit_id=None,
        unit_name=None,
        unit_number="101",
        project_id=None,
        project_name="SERENZ BY DANUBE",
        project_number=None,
        explicit_project_reference=None,
        project_reference_source="explicit",
        missing_fields=[],
        requires_clarification=False,
    )

    candidates = resolve_units(
        "101",
        UNITS,
        project_hint=intent.project_name,
    )

    assert candidates.status == "ambiguous"

    selected = select_candidate(
        "Tower A",
        candidates.units,
    )

    apply_selected_unit(
        intent,
        selected.units[0],
    )

    assert intent.unit_id == "id-srnz-a-101"
    assert intent.unit_number == "id-srnz-a-101"
    assert intent.requires_clarification is False


def test_sales_offer_reference_recovery():
    intent = SimpleNamespace(
        intent="sales_offer",
        inventory_operation=None,
        unit_id=None,
        unit_name=None,
        unit_number=None,
    )

    references = get_unit_references(
        intent,
        "sales offer of srnz 101",
    )

    assert references == [
        (None, "srnz 101")
    ]
