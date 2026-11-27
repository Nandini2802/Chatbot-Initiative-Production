from decimal import Decimal


AVAILABILITY_FILTER_KEYS = {
    "projectName",
    "Category__c",
    "ConstructionStatus",
    "FloorNumber__c",
    "SellingPrice__c",
    "Typology__c",
    "HandOverStatus",
    "View__c",
    "Location",
}


def as_filter_list(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, (list, tuple)):
        return [
            str(item)
            for item in value
            if item is not None and str(item).strip()
        ]

    if not str(value).strip():
        return []

    return [str(value)]


def format_price(value) -> str:
    return format(Decimal(str(value)), "f")


def build_listing_availability_filters(
    intent,
    displayed_units,
) -> dict[str, list[str]]:

    # Use actual project names from the inventory response.
    project_names = list(dict.fromkeys(
        unit.project_name
        for unit in displayed_units
        if unit.project_name
    ))

    if not project_names:
        return {}

    filters = {
        "projectName": project_names,
    }

    field_mapping = {
        "category": "Category__c",
        "construction_status": "ConstructionStatus",
        "floor_number": "FloorNumber__c",
        "handover_status": "HandOverStatus",
        "project_location": "Location",
    }

    for intent_field, api_field in field_mapping.items():
        values = as_filter_list(
            getattr(intent, intent_field, None)
        )
        
        if api_field == "HandOverStatus":
            values = [
                "off-plan"
                if value.strip().lower().replace("-", " ") == "off plan"
                else value
                for value in values
            ]

        # Convert numeric floor values to middleware format.
        if api_field == "FloorNumber__c":
            values = [
                f"Floor {value.strip()}"
                if value.strip().isdigit()
                else value
                for value in values
            ]

        if values:
            filters[api_field] = values

    min_price = getattr(intent, "min_price", None)
    max_price = getattr(intent, "max_price", None)

    if min_price is not None and max_price is not None:
        filters["SellingPrice__c"] = [
            f"{format_price(min_price)}-"
            f"{format_price(max_price)}"
        ]

    if getattr(intent, "view", None):
        matched_views = list(
            dict.fromkeys(
                unit.view
                for unit in displayed_units
                if unit.view and unit.view.strip()
            )
        )

        if matched_views:
            filters["View__c"] = matched_views

    # Handle both typology and unit_type using actual inventory values.
    if (
        getattr(intent, "typology", None)
        or getattr(intent, "unit_type", None)
    ):
        matched_typologies = list(
            dict.fromkeys(
                unit.typology
                for unit in displayed_units
                if unit.typology and unit.typology.strip()
            )
        )

        if matched_typologies:
            filters["Typology__c"] = matched_typologies


    # Preserve all actual view values from matched inventory units.
    if getattr(intent, "view", None):
        matched_views = list(
            dict.fromkeys(
                unit.view
                for unit in displayed_units
                if unit.view and unit.view.strip()
            )
        )

        if matched_views:
            filters["View__c"] = matched_views

    return filters

def get_unsupported_availability_filters(intent):
    unsupported = []

    fields = (
        "series",
        "unit_number",
        "min_area_sqft",
        "max_area_sqft",
        "min_floor",
        "max_floor",
        "price_selection",
    )

    for field in fields:
        value = getattr(intent, field, None)

        if value is not None and value != "":
            unsupported.append(field)

    # Bedrooms are already covered when an explicit
    # typology is available.
    bedrooms = getattr(intent, "bedrooms", None)
    typology = getattr(intent, "typology", None)

    if bedrooms is not None and not typology:
        unsupported.append("bedrooms")

    typology_values = as_filter_list(
        getattr(intent, "typology", None)
    )

    pool_covered = bool(typology_values) and all(
        "pool" in value.casefold()
        for value in typology_values
    )

    duplex_covered = bool(typology_values) and all(
        "duplex" in value.casefold()
        for value in typology_values
    )

    if getattr(intent, "requires_pool", False):
        if not pool_covered:
            unsupported.append("requires_pool")

    if getattr(intent, "requires_duplex", False):
        if not duplex_covered:
            unsupported.append("requires_duplex")

    min_price = getattr(intent, "min_price", None)
    max_price = getattr(intent, "max_price", None)

    if (min_price is None) != (max_price is None):
        unsupported.append("open_ended_price_range")

    status = getattr(intent, "status", None)

    if status and str(status).strip().casefold() != "available":
        unsupported.append("status")

    return unsupported