"""
Ambiguous project name settled by the router's choice (option B).

The router chooses from the same fixed project lists as the backend.
Its choice is used only when it is one of the ambiguous candidates found
in the user's message, and not a guess between numbered variants.
"""
import pytest

from app.services.project_context_service import (
    resolve_session_project,
    router_tiebreak,
)

SHAH = "SHAHRUKHZ BY DANUBE"
SHAH_RES = "SHAHRUKHZ RESIDENCES BY DANUBE"
ELZ = "ELZ RESIDENCE"
EL2 = "ELEGANZ 2 BY DANUBE"
EL5 = "ELEGANZ 5 BY DANUBE"
CANDS = (SHAH_RES, SHAH, ELZ)


# ---------------------------------------------------------------------------
# router_tiebreak
# ---------------------------------------------------------------------------

def test_router_choice_among_candidates_is_used():
    assert router_tiebreak(message="x", router_project=SHAH_RES, candidates=CANDS) == SHAH_RES


def test_router_choice_matched_case_and_suffix_insensitively():
    assert router_tiebreak(
        message="x", router_project="shahrukhz residences", candidates=CANDS
    ) == SHAH_RES


@pytest.mark.parametrize("router", [None, "", "GREENZ BY DANUBE", "SHAHRUKHZ TOWER"])
def test_router_choice_not_a_candidate_is_ignored(router):
    assert router_tiebreak(message="x", router_project=router, candidates=CANDS) is None


def test_no_candidates():
    assert router_tiebreak(message="x", router_project=SHAH_RES, candidates=()) is None


@pytest.mark.parametrize("message", ["Project code for eleganz", "eleganz project details"])
def test_numbered_family_guess_without_number_is_ignored(message):
    assert router_tiebreak(message=message, router_project=EL2, candidates=(EL2, EL5)) is None


@pytest.mark.parametrize("message", ["Project code for elegnz 2", "eleganz2 details"])
def test_numbered_family_with_typed_number_is_used(message):
    assert router_tiebreak(message=message, router_project=EL2, candidates=(EL2, EL5)) == EL2


def test_family_typed_number_must_be_the_chosen_one():
    assert router_tiebreak(
        message="Project code for elegnz 5", router_project=EL2, candidates=(EL2, EL5)
    ) is None


# ---------------------------------------------------------------------------
# resolve_session_project
# ---------------------------------------------------------------------------

ALLOWED = {SHAH, SHAH_RES, ELZ, "GREENZ BY DANUBE", EL2, EL5, "ELITZ BY DANUBE",
           "ELITZ 2 BY DANUBE", "ELITZ 3 BY DANUBE"}
TYPO = "Project code for sharukhz residences"


def decide(message, router, source="explicit", ref=None, **kw):
    return resolve_session_project(
        message=message, router_project=router, active_project=None,
        allowed_projects=ALLOWED, project_reference_source=source,
        explicit_project_reference=ref, **kw,
    )


def test_typo_resolved_by_router_choice():
    d = decide(TYPO, SHAH_RES, ref="sharukhz residences")
    assert (d.status, d.project_name, d.source, d.should_update_session) == (
        "matched", SHAH_RES, "explicit", True)


def test_typo_without_router_choice_still_ambiguous():
    d = decide(TYPO, None, ref="sharukhz residences")
    assert d.status == "ambiguous" and set(d.candidates) >= {SHAH, SHAH_RES}


@pytest.mark.parametrize("source", ["context", "none", "uncertain"])
def test_only_explicit_references_use_the_tiebreak(source):
    assert decide(TYPO, SHAH_RES, source=source).status == "ambiguous"


def test_tiebreak_can_be_switched_off_for_bank_details():
    d = decide(TYPO, SHAH_RES, ref="sharukhz residences", allow_router_tiebreak=False)
    assert d.status == "ambiguous"


@pytest.mark.parametrize("message,router,expected", [
    ("Project code for shahrukhz residences", SHAH_RES, SHAH_RES),   # exact: unchanged
    ("Project code for shahrukhz", SHAH, SHAH),                      # exact: unchanged
    ("Tell me about greenz", "GREENZ BY DANUBE", "GREENZ BY DANUBE"),
    ("Project code for elitz 2", "ELITZ 2 BY DANUBE", "ELITZ 2 BY DANUBE"),
])
def test_clear_names_unchanged(message, router, expected):
    d = decide(message, router, ref=message.split(" for ")[-1].replace("Tell me about ", ""))
    assert (d.status, d.project_name) == ("matched", expected)


def test_family_only_request_still_asks():
    # "eleganz" (no number) must not become ELEGANZ 2 even if the router picks it.
    d = decide("Project code for eleganz", EL2, ref="eleganz")
    assert d.status != "matched"
