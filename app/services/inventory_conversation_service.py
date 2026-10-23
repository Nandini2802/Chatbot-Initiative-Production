from app.services.project_name_service import normalize_project_name


def get_previous_inventory_context(response_payload: dict | None):
    if not isinstance(response_payload, dict):
        return None

    context = response_payload.get("inventory_context")

    if not isinstance(context, dict):
        return None

    if context.get("operation") not in {
        "unit_search",
        "unit_comparison",
        "unit_details",
    }:
        return None

    unit_ids = context.get("unit_ids", [])

    if not isinstance(unit_ids, list):
        return None

    return {
        "project_name": context.get("project_name"),
        "unit_ids": [str(uid) for uid in unit_ids if uid],
        "operation": context.get("operation"),
        "total_matches": context.get("total_matches", 0),
    }


def resolve_authorized_units(previous_context, inventory_snapshot):
    if not previous_context:
        return []

    allowed_ids = set(previous_context.get("unit_ids", []))

    return [
        unit
        for unit in inventory_snapshot.units
        if unit.unit_id and str(unit.unit_id) in allowed_ids
    ]


def build_inventory_context(intent, handler_result, inventory_snapshot):
    if not handler_result.has_data:
        return None

    context = handler_result.generation_context

    if context.get("service") != "inventory":
        return None

    operation = context.get("operation")

    if operation not in {
        "unit_search",
        "unit_comparison",
        "unit_details",
    }:
        return None

    unit_names = set()

    if operation == "unit_comparison":
        for comparison in context.get("comparisons", []):
            unit_name = comparison.get("unit", {}).get("unit_name")
            if unit_name:
                unit_names.add(unit_name)
    else:
        for unit in context.get("units", []):
            unit_name = unit.get("unit_name")
            if unit_name:
                unit_names.add(unit_name)

    selected_units = [
        unit
        for unit in inventory_snapshot.units
        if unit.unit_name in unit_names
        and (
            not intent.project_name
            or normalize_project_name(unit.project_name)
            == normalize_project_name(intent.project_name)
        )
    ]

    return {
        "project_name": intent.project_name,
        "unit_ids": [str(unit.unit_id) for unit in selected_units if unit.unit_id],
        "operation": operation,
        "total_matches": context.get("total_matches", len(selected_units)),
    }