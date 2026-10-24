
from app.schemas.retrieval import InventorySnapshot


class SalesOfferResolutionError(Exception):
    pass


def resolve_sales_offer_unit(
    intent,
    snapshot: InventorySnapshot,
):
    units = snapshot.units

    requested_unit = (
        intent.unit_id
        or intent.unit_name
        or intent.unit_number
    )

    if not requested_unit:
        raise SalesOfferResolutionError(
            "Please specify the unit for which "
            "you want to generate the sales offer."
        )

    requested_unit = str(requested_unit).strip().casefold()

    matches = []

    for unit in units:
        identifiers = [
            unit.unit_id,
            unit.unit_name,
            unit.unit_code,
        ]

        if any(
            str(value).strip().casefold() == requested_unit
            for value in identifiers
            if value
        ):
            matches.append(unit)

    if intent.project_id:
        matches = [
            unit for unit in matches
            if unit.project_id == intent.project_id
        ]

    if intent.project_name:
        from app.services.project_name_service import (
            normalize_project_name,
        )

        expected = normalize_project_name(
            intent.project_name
        )

        matches = [
            unit for unit in matches
            if unit.project_name
            and normalize_project_name(
                unit.project_name
            ) == expected
        ]

    if intent.project_number:
        matching_projects = {
            project.project_id
            for project in snapshot.projects
            if str(project.project_number) == str(
                intent.project_number
            )
        }

        matches = [
            unit for unit in matches
            if unit.project_id in matching_projects
        ]

    if not matches:
        raise SalesOfferResolutionError(
            "I couldn't find that unit in your "
            "authorized inventory."
        )

    unique = {
        unit.unit_id: unit
        for unit in matches
        if unit.unit_id
    }

    if len(unique) != 1:
        raise SalesOfferResolutionError(
            "Multiple units match your request. "
            "Please provide the complete unit name or ID."
        )

    return next(iter(unique.values()))
