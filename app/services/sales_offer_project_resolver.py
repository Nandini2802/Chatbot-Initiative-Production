
import re
from dataclasses import dataclass

from app.services.project_name_service import (
    normalize_project_name,
)


@dataclass(frozen=True)
class SalesOfferProjectMatch:
    status: str
    project: object | None = None
    candidates: tuple[str, ...] = ()


PROJECT_ALIASES = {
    "breez": "breeze",
    "jewelz": "jewelz residence",
    "wavez": "wavez residence",
    "olivz": "olivz residence",
    "elz": "elz residence",
    "lawnz": "lawnz residence",
    "miraclz": "miraclz tower",
    "glamz": "glamz residence",
    "starz": "starz tower",
    "glitz 1": "glitz residence 1",
    "glitz 2": "glitz residence 2",
    "glitz 3": "glitz residence 3",
    "bayz101": "bayz 101",
    "bayz102": "bayz 102",
    "shahrukhz residences":
        "shahrukhz residences",
    "shahrukhz": "shahrukhz",
    "resortz": "resortz residence",
}


def normalize_sales_offer_name(value):
    name = normalize_project_name(value)

    # BAYZ101 -> bayz 101
    name = re.sub(
        r"(?<=[a-z])(?=\d)",
        " ",
        name,
    )

    # Apply exact aliases only.
    return PROJECT_ALIASES.get(name, name)


def _family_name(value):
    """
    Remove an optional numbered variant.

    glitz residence 3 -> glitz residence
    oceanz 2 -> oceanz
    """
    return re.sub(
        r"\s+\d+$",
        "",
        value,
    )


def _project_label(project):
    return str(project.project_name or "").strip()


def resolve_sales_offer_project(
    reference,
    snapshot,
):
    """
    Resolve against the live inventory projects.

    Returns:
      matched   -> exactly one project
      ambiguous -> multiple possible projects
      not_found -> no project

    Does not grant access to units.
    """

    requested = normalize_sales_offer_name(reference)

    if not requested:
        return SalesOfferProjectMatch("not_found")

    projects = [
        project
        for project in snapshot.projects
        if project.project_id
        and project.project_name
    ]

    # 1. Exact canonical name or alias.
    exact = [
        project
        for project in projects
        if normalize_sales_offer_name(
            project.project_name
        ) == requested
    ]

    # Deduplicate by Salesforce project ID.
    exact = {
        project.project_id: project
        for project in exact
    }

    if len(exact) == 1:
        return SalesOfferProjectMatch(
            "matched",
            next(iter(exact.values())),
        )

    if len(exact) > 1:
        return SalesOfferProjectMatch(
            "ambiguous",
            candidates=tuple(sorted(
                _project_label(p)
                for p in exact.values()
            )),
        )

    # 2. Family matching.
    # Only match complete family names, never
    # arbitrary substrings or unrelated projects.
    family_matches = {}

    for project in projects:
        name = normalize_sales_offer_name(
            project.project_name
        )

        family = _family_name(name)

        if requested == family:
            family_matches[project.project_id] = project

    if len(family_matches) == 1:
        return SalesOfferProjectMatch(
            "matched",
            next(iter(family_matches.values())),
        )

    if len(family_matches) > 1:
        return SalesOfferProjectMatch(
            "ambiguous",
            candidates=tuple(sorted(
                _project_label(p)
                for p in family_matches.values()
            )),
        )

    return SalesOfferProjectMatch("not_found")
