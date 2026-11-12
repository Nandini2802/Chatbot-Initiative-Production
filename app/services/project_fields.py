"""
Direct answers to specific project questions (project_operation="field").

Values come only from the Projects API record. "Project code" is answered
with the project number (projectNumber). Answers are built from fixed
text; no LLM writes them, so values cannot be invented.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Iterable


# field -> user-facing label
FIELD_LABELS = {
    "project_number": "project number",
    "project_code": "project code",
    "project_configuration": "project configuration",
    "places_nearby": "places nearby",
    "location": "location",
    "bedrooms_categories": "bedroom options",
    "apartments": "number of apartments",
    "construction_status": "construction status",
    "completion_date": "expected completion",
    "handover_date": "handover date",
    "payment_plan": "payment plan",
    "starting_price": "starting price",
    "service_charge": "service charge",
    "amenities": "amenities",
    "building_type": "building type",
    "plot_size_sqft": "plot size",
    "total_units": "total units",
    "total_sold_units": "total sold units",
    "total_booked_units": "total booked units",
    "total_residential_units": "total residential units",
    "total_commercial_units": "total commercial units",
    "total_other_units": "total other units",
    "total_new_units": "total new units",
    "total_buildings": "total buildings",
    "total_floors": "total floors",
    "total_bua_sqft": "total built-up area",
    "total_saleable_area": "total saleable area",
}

# "all_totals" expands to these, in this order.
TOTAL_FIELDS = (
    "total_units",
    "total_sold_units",
    "total_booked_units",
    "total_residential_units",
    "total_commercial_units",
    "total_other_units",
    "total_new_units",
    "total_buildings",
    "total_floors",
    "total_bua_sqft",
    "total_saleable_area",
)

AREA_FIELDS = {"plot_size_sqft", "total_bua_sqft", "total_saleable_area"}
COUNT_FIELDS = set(TOTAL_FIELDS) - AREA_FIELDS | {"apartments"}

MAX_FIELDS = len(FIELD_LABELS)

# Fields answered from another Projects API field.
# The Projects API has no project code; it is the project number.
FIELD_SOURCES = {
    "project_code": "project_number",
}


def expand_fields(fields: Iterable[str] | None) -> list[str]:
    """
    Known fields only, "all_totals" expanded, duplicates removed, order kept.
    "project_code" and "project_number" are the same value: when both are
    requested only "project_code" is kept (one row, labelled as asked).
    """

    result: list[str] = []

    for field in fields or ():
        names = TOTAL_FIELDS if field == "all_totals" else (field,)

        for name in names:
            if name in FIELD_LABELS and name not in result:
                result.append(name)

    if "project_code" in result and "project_number" in result:
        result.remove("project_number")

    return result[:MAX_FIELDS]


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, tuple, set, dict)) and not value:
        return True
    return False


def _format_number(value) -> str:
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return str(value).strip()

    if number == number.to_integral_value():
        return f"{int(number):,}"

    return f"{number:,.2f}"


def format_field_value(field: str, value, project=None) -> str | None:
    """Display text for a field value, or None when it is empty."""

    if _is_empty(value):
        return None

    if isinstance(value, (list, tuple, set)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(parts) if parts else None

    if isinstance(value, dict):
        return None

    text = str(value).strip()

    if field in COUNT_FIELDS:
        return _format_number(text)

    if field in AREA_FIELDS:
        unit = str(
            getattr(project, "unit_of_measurement", "") or "square feet"
        ).strip().lower()
        return f"{_format_number(text)} {unit}"

    if field == "starting_price":
        formatted = _format_number(text)
        return formatted if "aed" in formatted.lower() else f"AED {formatted}"

    return text


def field_rows(project, fields: list[str]) -> list[dict]:
    """
    [{"field", "label", "value"}] from the Projects API record.
    value is None when not available.
    """

    rows = []

    for field in fields:
        raw = getattr(
            project,
            FIELD_SOURCES.get(field, field),
            None,
        )

        rows.append({
            "field": field,
            "label": FIELD_LABELS[field],
            "value": format_field_value(field, raw, project),
        })

    return rows


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def build_field_answer(project_name: str, rows: list[dict]) -> str:
    """
    One field   -> "The handover date for X is 2030-07-01."
    Up to 3     -> one sentence per field.
    More        -> "Here are the requested details for X."
    Missing     -> "Places nearby isn't available for X."
    """

    if not rows:
        return f"I couldn't find that information for {project_name}."

    if len(rows) > 3:
        return f"Here are the requested details for {project_name}."

    sentences = []

    for row in rows:
        if row["value"]:
            sentences.append(
                f"The {row['label']} for {project_name} is {row['value']}."
            )
        else:
            sentences.append(
                f"{_capitalize(row['label'])} isn't available for {project_name}."
            )

    return " ".join(sentences)
