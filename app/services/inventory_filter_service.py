from decimal import Decimal, InvalidOperation
import re

from app.schemas.retrieval import InventoryUnit
from app.schemas.routing import RoutingIntent
from app.services.inventory_attribute_resolver import (
    InventoryAttributeResolver as Resolver,
    normalize_text,
)


def norm(value) -> str:
    return str(value or "").strip().casefold()


def as_decimal(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        cleaned = str(value).replace(",", "").strip()
        if not cleaned:
            return None

        number = Decimal(cleaned)
        return number if number.is_finite() else None

    except (InvalidOperation, ValueError):
        return None


def as_bedrooms(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None

    text = norm(value)

    if text in {"studio", "st", "0", "0.0"}:
        return 0

    match = re.fullmatch(
        r"(\d+)(?:\.0+)?"
        r"(?:\s*(?:br|bed|beds|bedroom|bedrooms|bhk))?",
        text,
    )

    return int(match.group(1)) if match else None


def inferred_bedrooms(unit: InventoryUnit) -> int | None:
    # Prefer the dedicated Salesforce field.
    direct = as_bedrooms(unit.bedrooms)

    if direct is not None:
        return direct

    # Derive from descriptive fields only when reliable.
    for value in (unit.unit_type, unit.typology):
        text = normalize_text(value)

        if text == "studio" or text.startswith("studio "):
            return 0

        match = re.search(
            r"\b(\d+)\s*(?:bed|beds|bedroom|bedrooms|bhk)\b",
            text,
        )

        if match:
            return int(match.group(1))

    return None


class InventoryFilterService:

    def filter_units(
        self,
        units: list[InventoryUnit],
        intent: RoutingIntent,
    ) -> list[InventoryUnit]:

        results = []

        for unit in units:

            # Project
            if intent.project_name:
                from app.services.project_name_service import (
                    normalize_project_name,
                )

                if (
                    normalize_project_name(unit.project_name or "")
                    != normalize_project_name(intent.project_name)
                ):
                    continue

            # Unit identifier remains exact.
            if intent.unit_number:
                requested = norm(intent.unit_number)

                if requested not in {
                    norm(unit.unit_name),
                    norm(unit.unit_code),
                    norm(unit.unit_id),
                }:
                    continue

            # Location
            if intent.project_location:
                if not Resolver.match(
                    intent.project_location,
                    unit.project_location,
                ):
                    continue

            # Availability
            if intent.status:
                if normalize_text(intent.status) != normalize_text(
                    unit.status
                ):
                    continue

            # Category
            if intent.category:
                if not Resolver.match(
                    intent.category, unit.category
                ):
                    continue

            # Bedrooms
            if intent.bedrooms is not None:
                if inferred_bedrooms(unit) != intent.bedrooms:
                    continue

            # Unit type
            if intent.unit_type:
                if not Resolver.match(
                    intent.unit_type, unit.unit_type
                ):
                    continue

            # Typology
            if intent.typology:
                if not Resolver.match(
                    intent.typology, unit.typology
                ):
                    continue

            # View
            if intent.view:
                if not Resolver.match_view(
                    intent.view, unit.view
                ):
                    continue

            # Handover
            if intent.handover_status:
                if normalize_text(
                    intent.handover_status
                ) != normalize_text(unit.handover_status):
                    continue

            # Construction
            if intent.construction_status:
                if normalize_text(
                    intent.construction_status
                ) != normalize_text(unit.construction_status):
                    continue

            # Special typology qualifiers
            description = normalize_text(
                f"{unit.typology or ''} "
                f"{unit.unit_type or ''}"
            )

            if intent.requires_pool:
                if "pool" not in description.split():
                    continue

            if intent.requires_duplex:
                if "duplex" not in description.split():
                    continue

            # Floor
            if intent.floor_number:
                if norm(unit.floor_number) != norm(
                    intent.floor_number
                ):
                    continue

            # Currency
            if intent.currency:
                if normalize_text(unit.currency) != normalize_text(
                    intent.currency
                ):
                    continue

            # Price
            price = as_decimal(unit.price)

            if intent.min_price is not None:
                if (
                    price is None
                    or price < Decimal(str(intent.min_price))
                ):
                    continue

            if intent.max_price is not None:
                if (
                    price is None
                    or price > Decimal(str(intent.max_price))
                ):
                    continue

            # Area
            area = as_decimal(unit.area_sqft)

            if intent.min_area_sqft is not None:
                if (
                    area is None
                    or area < Decimal(str(intent.min_area_sqft))
                ):
                    continue

            if intent.max_area_sqft is not None:
                if (
                    area is None
                    or area > Decimal(str(intent.max_area_sqft))
                ):
                    continue

            results.append(unit)

        # Sorting
        if intent.sort_by:
            sort_fields = {
                "price_asc": ("price", False),
                "price_desc": ("price", True),
                "area_asc": ("area_sqft", False),
                "area_desc": ("area_sqft", True),
            }

            field, reverse = sort_fields[intent.sort_by]

            known = [
                unit for unit in results
                if as_decimal(getattr(unit, field)) is not None
            ]

            unknown = [
                unit for unit in results
                if as_decimal(getattr(unit, field)) is None
            ]

            known.sort(
                key=lambda unit: as_decimal(
                    getattr(unit, field)
                ),
                reverse=reverse,
            )

            results = known + unknown

        return results