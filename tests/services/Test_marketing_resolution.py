
import pytest

from app.services.marketing_resolution import (
    resolve_marketing_project,
    resolve_marketing_asset,
    resolve_assets,
)


MARKETING_PROJECTS = [
    "Shahrukhz Residences",
    "Greenz",
    "Breez",
    "Shahrukhz",
    "Serenz",
    "Aspirz",
    "Sparklz",
    "DIAMONDZ",
    "Timez",
    "Bayz 102",
    "Oasiz",
    "Oasiz 2",
    "BAYZ",
    "OCEANZ",
    "SPORTZ",
    "ELITZ 3",
    "Elitz 2",
    "Skyz",
    "Opalz",
    "ELEGANZ",
    "Gemz",
    "Pearlz",
    "Jewelz",
    "Wavez",
    "Olivz",
    "Elz",
    "Lawnz",
    "Miraclz",
    "Resortz",
    "Glamz",
    "Starz",
    "Glitz 1",
    "Glitz 2",
    "Glitz 3",
    "Dreamz",
    "FASHIONZ",
    "Viewz",
    "Elitz",
    "Petalz",
]


@pytest.mark.parametrize("reference,expected", [
    ("Greenz", "Greenz"),
    ("Greenz by Danube", "Greenz"),
    ("Greens", "Greenz"),

    ("Eleganz", "ELEGANZ"),
    ("ELEGANZ 1 BY DANUBE", "ELEGANZ"),
    ("ELEGANZ 2 BY DANUBE", "ELEGANZ"),
    ("ELEGANZ 3 BY DANUBE", "ELEGANZ"),
    ("ELEGANZ 4 BY DANUBE", "ELEGANZ"),
    ("ELEGANZ 5 BY DANUBE", "ELEGANZ"),
    ("ELEGANZ 6 BY DANUBE", "ELEGANZ"),

    ("Bayz 102", "Bayz 102"),
    ("Bayz", "BAYZ"),

    ("Oasiz 2", "Oasiz 2"),
    ("Elitz 2", "Elitz 2"),
    ("Glitz 3", "Glitz 3"),

    ("Shahrukhz Residences", "Shahrukhz Residences"),
    ("Shahrukhz", "Shahrukhz"),

    ("Serenz", "Serenz"),
    ("Serens", "Serenz"),
])
def test_project_resolution(reference, expected):
    result = resolve_marketing_project(
        reference,
        MARKETING_PROJECTS,
    )

    assert result.status == "matched"
    assert result.name == expected



@pytest.mark.parametrize("reference", [
    "ELEGANZ 7 BY DANUBE",
    "Glitz 4",
    "Elitz 5",
    "Bayz 103",
    "Totally Unknown Development",
])
def test_unapproved_names_not_silently_mapped(reference):
    result = resolve_marketing_project(
        reference,
        MARKETING_PROJECTS,
    )

    assert result.status != "matched"


def test_unknown_project():
    result = resolve_marketing_project(
        "Unknown Property XYZ",
        MARKETING_PROJECTS,
    )

    assert result.status == "not_found"
    assert result.name is None


def test_empty_project_reference():
    result = resolve_marketing_project(
        "",
        MARKETING_PROJECTS,
    )

    assert result.status == "not_found"


def test_empty_marketing_catalog():
    result = resolve_marketing_project(
        "Greenz",
        [],
    )

    assert result.status == "not_found"


@pytest.mark.parametrize("value,expected", [
    # Floor plans
    ("floor plan", "floor plan"),
    ("floor plans", "floor plan"),
    ("floorplan", "floor plan"),
    ("flor plans", "floor plan"),

    # Brochures
    ("brochure", "brochure"),
    ("brochures", "brochure"),
    ("brochre", "brochure"),
    ("brochr", "brochure"),

    # Videos
    ("video", "video"),
    ("videos", "video"),
    ("vidio", "video"),
    ("vedio", "video"),

    # Amenities
    ("amenities", "amenities"),
    ("amenity", "amenities"),
    ("amnties", "amenities"),
    ("amenties", "amenities"),

    # Exterior
    ("exterior", "exterior"),
    ("exteriors", "exterior"),
    ("exterir", "exterior"),

    # Interiors
    ("interior", "interiors"),
    ("interiors", "interiors"),
    ("interir", "interiors"),

    # PPT
    ("ppt", "ppt"),
    ("pptx", "ppt"),
    ("presentation", "ppt"),
    ("powerpoint", "ppt"),

    # Renders
    ("render", "renders"),
    ("renders", "renders"),
    ("rendering", "renders"),
    ("rander", "renders"),

    # Price list
    ("price list", "price list"),
    ("price lists", "price list"),
    ("pricelist", "price list"),
    ("price sheet", "price list"),

    # All marketing materials
    ("all marketing materials", "all"),
    ("all collateral", "all"),
    ("all materials", "all"),

    # Social media
    ("social media", "social-media"),
    ("social media assets", "social-media"),

    # Factsheet
    ("factsheet", "factsheet"),
    ("fact sheet", "factsheet"),

    # Other
    ("other materials", "other"),

    # Walkthrough
    ("walkthrough", "walkthrough"),
    ("walk through", "walkthrough"),
    ("walkthrough video", "walkthrough"),
])
def test_marketing_material_typo(value, expected):
    result = resolve_marketing_asset(value)

    assert result.status == "matched"
    assert result.name == expected



def test_multiple_materials():
    resolved, unresolved = resolve_assets([
        "brochre",
        "amnties",
        "vidio",
    ])

    assert resolved == [
        "brochure",
        "amenities",
        "video",
    ]

    assert unresolved == []


def test_multiple_materials_with_duplicates():
    resolved, unresolved = resolve_assets([
        "brochure",
        "brochre",
        "brochures",
        "video",
        "vidio",
    ])

    assert resolved == [
        "brochure",
        "video",
    ]

    assert unresolved == []


def test_empty_marketing_materials():
    resolved, unresolved = resolve_assets([])

    assert resolved == []
    assert unresolved == []


def test_unknown_marketing_material():
    result = resolve_marketing_asset(
        "completely unrelated request"
    )

    assert result.status == "not_found"
    assert result.name is None


def test_repeated_project_query_consistency():
    results = [
        resolve_marketing_project(
            "Greens",
            MARKETING_PROJECTS,
        )
        for _ in range(20)
    ]

    assert all(
        result.status == "matched"
        and result.name == "Greenz"
        for result in results
    )


def test_repeated_material_query_consistency():
    results = [
        resolve_marketing_asset("amnties")
        for _ in range(20)
    ]

    assert all(
        result.status == "matched"
        and result.name == "amenities"
        for result in results
    )
