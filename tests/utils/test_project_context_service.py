
from app.services.project_context_service import (
    resolve_session_project,
)


PROJECTS = {
    "Oceanz 2",
    "Oceanz 3",
    "Breez",
    "Greenz",
}


def test_inherit_existing_project():
    result = resolve_session_project(
        message="Check payment plans",
        router_project="Oceanz 2",
        active_project="Oceanz 2",
        allowed_projects=PROJECTS,
        project_reference_source="context",
    )

    assert result.status == "matched"
    assert result.project_name == "Oceanz 2"
    assert result.source == "session"
    assert result.should_update_session is False


def test_explicit_project_switch():
    result = resolve_session_project(
        message="Show brochure for Breez",
        router_project="Breez",
        active_project="Oceanz 2",
        allowed_projects=PROJECTS,
        project_reference_source="explicit",
        explicit_project_reference="Breez",
    )

    assert result.status == "matched"
    assert result.project_name == "Breez"
    assert result.should_update_session is True


def test_unknown_explicit_project():
    result = resolve_session_project(
        message="Payment plans for Unknown Towers",
        router_project=None,
        active_project="Oceanz 2",
        allowed_projects=PROJECTS,
        project_reference_source="explicit",
        explicit_project_reference="Unknown Towers",
    )

    assert result.status == "unresolved_explicit"
    assert result.project_name is None


def test_new_project_number_not_in_catalog():
    result = resolve_session_project(
        message="Payment plans for Oceanz 9",
        router_project=None,
        active_project="Oceanz 2",
        allowed_projects=PROJECTS,
        project_reference_source="explicit",
        explicit_project_reference="Oceanz 9",
    )

    assert result.status == "unresolved_explicit"
    assert result.project_name is None


def test_missing_explicit_reference():
    result = resolve_session_project(
        message="Payment plans for another project",
        router_project=None,
        active_project="Oceanz 2",
        allowed_projects=PROJECTS,
        project_reference_source="explicit",
        explicit_project_reference=None,
    )

    assert result.status == "unresolved_explicit"


def test_uncertain_project_reference():
    result = resolve_session_project(
        message="Check that other project's plans",
        router_project=None,
        active_project="Oceanz 2",
        allowed_projects=PROJECTS,
        project_reference_source="uncertain",
    )

    assert result.status == "unresolved_explicit"
    assert result.project_name is None


def test_bank_account_index_not_project_switch():
    result = resolve_session_project(
        message="Show escrow account 1",
        router_project="Oceanz 2",
        active_project="Oceanz 2",
        allowed_projects=PROJECTS,
        project_reference_source="context",
    )

    assert result.status == "matched"
    assert result.project_name == "Oceanz 2"
    assert result.source == "session"


def test_no_project_in_new_session():
    result = resolve_session_project(
        message="Check payment plans",
        router_project=None,
        active_project=None,
        allowed_projects=PROJECTS,
        project_reference_source="none",
    )

    assert result.status == "not_found"
