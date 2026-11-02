
from app.services.marketing_resolution import (
    extract_marketing_parts,
    resolve_marketing_project,
)

catalog = [
    "Shahrukhz Residences",
    "Shahrukhz",
    "Greenz",
    "Breez",
    "Aspirz",
    "Glamz",
    "Timez",
    "Viewz",
    "FASHIONZ",
    "OCEANZ",
    "Oasiz",
    "Oasiz 2",
]

queries = [
    "brochure of Shahrukhz Residences",
    "sharukhz residence brochure",
    "Shahrukhz video",
    "shahrukz vidoe",
    "glemz video",
    "sharukhs brochure",
    "sharukhz residnces brochure",
    "brochure of SHAHRUKHZ RESIDENCES BY DANUBE",
    "SHAHRUKHZ BY DANUBE video",
    "Timez",
    "VIEWZ 1 BY DANUBE amenities",
    "VIEWZ 2 BY DANUBE exterior",
    "FASHIONZ 1 BY DANUBE interiors",
    "OCEANZ 1 BY DANUBE price list",
    "OCEANZ 2 BY DANUBE brochure",
    "OCEANZ 3 BY DANUBE floor plan",
    "OASIZ 1 BY DANUBE amenities",
]

for query in queries:
    project, assets = extract_marketing_parts(
        query
    )

    result = resolve_marketing_project(
        project,
        catalog,
    )

    print(
        f"\nQuery: {query}"
        f"\nExtracted: {project}"
        f"\nProject: {result.name}"
        f"\nStatus: {result.status}"
        f"\nMethod: {result.method}"
        f"\nAssets: {assets}"
    )

from app.services.marketing_resolution import (
    extract_marketing_parts,
)


def test_asset_first_extraction():
    project, assets = extract_marketing_parts(
        "brochure of Shahrukhz Residences"
    )

    assert project == "shahrukhz residences"
    assert assets == ["brochure"]


def test_project_first_extraction():
    project, assets = extract_marketing_parts(
        "Bayz 102 brochure"
    )

    assert project == "bayz 102"
    assert assets == ["brochure"]


def test_typo_asset_extraction():
    project, assets = extract_marketing_parts(
        "shahrukz vidoe"
    )

    assert project == "shahrukz"
    assert assets == ["video"]


def test_project_only_extraction():
    project, assets = extract_marketing_parts(
        "Timez"
    )

    assert project == "timez"
    assert assets == []