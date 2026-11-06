
import pytest

from app.services.project_resolution_service import (
    parse_comparison_references,
    resolve_comparison_project,
    extract_comparison_projects,
    format_project_comparison_clarification,
)


# Test fixture only.
# Production validation uses the live Active Projects catalog.
PROJECTS = [
    "ELEGANZ BY DANUBE",
    "GREENZ BY DANUBE",
    "ELITZ BY DANUBE",
    "ELITZ 2 BY DANUBE",
]


def feedback(query):
    references = parse_comparison_references(query)
    resolutions = [
        resolve_comparison_project(name, PROJECTS)
        for name in references
    ]
    return format_project_comparison_clarification(
        references,
        resolutions,
    )


def test_extract_original_names():
    result = parse_comparison_references(
        "compare SERENZ vs ELEGANZ"
    )
    assert result == ["SERENZ", "ELEGANZ"]


def test_first_project_missing():
    response = feedback(
        "compare UNKNOWNXYZ vs ELEGANZ"
    )
    assert "UNKNOWNXYZ" in response
    assert "ELEGANZ BY DANUBE" in response
    assert "couldn't find" in response


def test_second_project_missing():
    response = feedback(
        "compare ELEGANZ vs UNKNOWNXYZ"
    )
    assert "UNKNOWNXYZ" in response
    assert "ELEGANZ BY DANUBE" in response


def test_both_projects_missing():
    response = feedback(
        "compare UNKNOWNAAA vs UNKNOWNBBB"
    )
    assert "UNKNOWNAAA" in response
    assert "UNKNOWNBBB" in response


def test_both_projects_valid():
    result = extract_comparison_projects(
        "compare GREENZ vs ELEGANZ",
        PROJECTS,
    )
    assert result == [
        "GREENZ BY DANUBE",
        "ELEGANZ BY DANUBE",
    ]


def test_same_project_twice():
    response = feedback(
        "compare ELEGANZ vs ELEGANZ"
    )
    assert "two different" in response


def test_explicit_missing_variant():
    response = feedback(
        "compare ELITZ 9 vs ELEGANZ"
    )
    assert "ELITZ 9" in response
    assert "couldn't find" in response


def test_supported_comparison_separators():
    for separator in ["and", "with", "vs", "versus"]:
        result = parse_comparison_references(
            f"compare GREENZ {separator} ELEGANZ"
        )
        assert result == ["GREENZ", "ELEGANZ"]


def test_unnumbered_project_resolves():
    result = resolve_comparison_project(
        "ELITZ",
        PROJECTS,
    )
    assert result.name == "ELITZ BY DANUBE"


def test_invalid_query_is_not_comparison():
    assert parse_comparison_references(
        "Give me the brochure of ELEGANZ"
    ) == []
