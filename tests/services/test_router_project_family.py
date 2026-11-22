
from app.services.project_selection_service import (
    projects_in_router_family,
    find_project_candidates,
)
from app.schemas.routing import RoutingIntent


CATALOG = [
    "BAYZ 101 BY DANUBE",
    "BAYZ 102 BY DANUBE",
    "OASIZ 1 BY DANUBE",
    "OASIZ 2 BY DANUBE",
    "SHAHRUKHZ BY DANUBE",
    "SHAHRUKHZ RESIDENCES BY DANUBE",
    "GREENZ BY DANUBE",
]


def test_router_family_returns_all_bayz_variants():
    matches = projects_in_router_family(
        "BAYZ",
        CATALOG,
    )

    assert matches == [
        "BAYZ 101 BY DANUBE",
        "BAYZ 102 BY DANUBE",
    ]


def test_router_family_returns_all_oasiz_variants():
    matches = projects_in_router_family(
        "OASIZ",
        CATALOG,
    )

    assert matches == [
        "OASIZ 1 BY DANUBE",
        "OASIZ 2 BY DANUBE",
    ]


def test_router_family_does_not_invent_projects():
    assert projects_in_router_family(
        "UNKNOWN",
        CATALOG,
    ) == []


def test_router_family_is_catalog_scoped():
    assert projects_in_router_family(
        "BAYZ",
        ["GREENZ BY DANUBE"],
    ) == []


def test_specific_project_still_has_own_identity():
    matches = projects_in_router_family(
        "SHAHRUKHZ",
        CATALOG,
    )

    assert "SHAHRUKHZ BY DANUBE" in matches
    assert "SHAHRUKHZ RESIDENCES BY DANUBE" in matches


def test_existing_exact_family_matching():
    assert find_project_candidates(
        "bayz",
        CATALOG,
    ) == [
        "BAYZ 101 BY DANUBE",
        "BAYZ 102 BY DANUBE",
    ]


def test_router_schema_accepts_project_family():
    intent = RoutingIntent.model_construct(
        intent="inventory",
        project_name=None,
        project_family="BAYZ",
        explicit_project_reference="bays",
        project_reference_source="explicit",
    )

    assert intent.project_family == "BAYZ"
    assert intent.project_name is None
