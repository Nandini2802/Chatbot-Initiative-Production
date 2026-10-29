
import re

from app.services.project_name_service import (
    normalize_project_name,
)


class SalesOfferResolutionError(Exception):
    pass


def normalize_unit_identifier(value: str | None) -> str:
    """
    GRZ-TH-808 -> grzth808
    grzth808   -> grzth808
    """
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").casefold(),
    )


def find_project_units(intent, snapshot):
    """
    Resolve a project name, Salesforce project ID,
    or project number against authorized inventory.
    """

    requested_ids = set()
    requested_names = set()

    if getattr(intent, "project_id", None):
        requested_ids.add(
            str(intent.project_id).strip().casefold()
        )

    if getattr(intent, "project_name", None):
        requested_names.add(
            normalize_project_name(intent.project_name)
        )

    if getattr(intent, "project_number", None):
        requested_number = str(
            intent.project_number
        ).strip().casefold()

        for project in snapshot.projects:
            if (
                project.project_id
                and str(
                    project.project_number or ""
                ).strip().casefold() == requested_number
            ):
                requested_ids.add(
                    project.project_id.casefold()
                )

    # Resolve project names to their IDs.
    for project in snapshot.projects:
        if (
            project.project_id
            and normalize_project_name(
                project.project_name or ""
            ) in requested_names
        ):
            requested_ids.add(
                project.project_id.casefold()
            )

    return [
        unit
        for unit in snapshot.units
        if unit.unit_id
        and (
            (
                unit.project_id
                and unit.project_id.casefold()
                in requested_ids
            )
            or (
                unit.project_name
                and normalize_project_name(
                    unit.project_name
                ) in requested_names
            )
        )
    ]


def find_unit(
    requested,
    snapshot,
    allowed_unit_ids=None,
):
    """
    Returns:
        (unit, False): exact match
        (unit, True): normalized match requiring confirmation

    Never chooses an ambiguous match.
    """

    requested = str(requested or "").strip()

    if not requested:
        raise SalesOfferResolutionError(
            "Please specify the unit for which "
            "you want to generate the sales offer."
        )

    allowed = (
        set(allowed_unit_ids)
        if allowed_unit_ids is not None
        else None
    )

    units = [
        unit
        for unit in snapshot.units
        if unit.unit_id
        and (
            allowed is None
            or unit.unit_id in allowed
        )
    ]

    exact_matches = {
        unit.unit_id: unit
        for unit in units
        if any(
            str(value).strip().casefold()
            == requested.casefold()
            for value in (
                unit.unit_id,
                unit.unit_name,
                unit.unit_code,
            )
            if value
        )
    }

    if len(exact_matches) == 1:
        return next(iter(exact_matches.values())), False

    if len(exact_matches) > 1:
        raise SalesOfferResolutionError(
            "Multiple units match your request. "
            "Please provide the exact unit ID."
        )

    normalized = normalize_unit_identifier(requested)

    if not normalized:
        raise SalesOfferResolutionError(
            "Please specify a valid unit name or ID."
        )

    normalized_matches = {
        unit.unit_id: unit
        for unit in units
        if any(
            normalize_unit_identifier(value)
            == normalized
            for value in (
                unit.unit_name,
                unit.unit_code,
            )
            if value
        )
    }

    if len(normalized_matches) == 1:
        return (
            next(iter(normalized_matches.values())),
            True,
        )

    if len(normalized_matches) > 1:
        raise SalesOfferResolutionError(
            "Multiple units match that reference. "
            "Please provide the complete unit name or ID."
        )

    raise SalesOfferResolutionError(
        "I couldn't find that unit in your "
        "authorized inventory."
    )
