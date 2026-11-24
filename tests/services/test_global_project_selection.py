"""Unit tests for the shared global project-selection helpers."""
import pytest

from app.services.project_selection_service import (
    find_project_candidates,
    project_mention_candidates,
    interpret_project_selection,
    project_selection_question,
)
from app.services.project_selection_state import ProjectSelectionState

from app.services.project_selection_service import (
    matching_projects,
)
from app.services.project_resolution_service import (
    match_project_reference,
    match_project_in_message,
    match_unique_specific_variant,
)



CATALOG = [
    "SHAHRUKHZ BY DANUBE",
    "SHAHRUKHZ RESIDENCES BY DANUBE",
    "BAYZ 101 BY DANUBE",
    "BAYZ 102 BY DANUBE",
    "OASIZ 1 BY DANUBE",
    "OASIZ 2 BY DANUBE",
]


@pytest.mark.parametrize("reference", ["shahrukh", "shahrukhz", "SHahrukhZ"])
def test_shahrukh_family_is_ambiguous(reference):
    assert find_project_candidates(reference, CATALOG) == CATALOG[:2]


def test_bank_message_uses_actual_user_reference_even_if_router_guessed():
    found, matches = project_mention_candidates("bank account of shahrukh", CATALOG)
    assert found and matches == CATALOG[:2]


@pytest.mark.parametrize("message", [
    "give me brochure of shahrukhz", "payment plan of shahrukhz",
    "download availability of shahrukhz", "sales offer of shahrukhz",
    "show units of shahrukhz", "project information shahrukhz",
])
def test_every_intent_message_uses_one_ambiguity_rule(message):
    found, candidates = project_mention_candidates(message, CATALOG)
    assert found and candidates == CATALOG[:2]


def test_full_and_residence_short_names_are_unique():
    for message in [
        "bank account of SHAHRUKHZ BY DANUBE",
        "bank account of Shahrukhz Residences",
    ]:
        found, candidates = project_mention_candidates(message, CATALOG)
        assert found and not candidates


def test_bayz_family_but_not_numbered_project():
    assert len(find_project_candidates("bayz", CATALOG)) == 2
    assert find_project_candidates("bayz 101", CATALOG) == []
    assert find_project_candidates("bayz101", CATALOG) == []


def test_oasiz_family_but_not_numbered_project():
    assert len(find_project_candidates("oasiz", CATALOG)) == 2
    assert find_project_candidates("oasiz 2", CATALOG) == []


def test_both_and_ordinal_and_exact_followups():
    choices = CATALOG[:2]
    assert interpret_project_selection("Both", choices).projects == tuple(choices)
    assert interpret_project_selection("first", choices).projects == (choices[0],)
    assert interpret_project_selection("2", choices).projects == (choices[1],)
    assert interpret_project_selection("second one", choices).projects == (choices[1],)
    assert interpret_project_selection("SHAHRUKHZ RESIDENCES BY DANUBE", choices).projects == (choices[1],)
    assert interpret_project_selection("cancel", choices).status == "cancelled"
    assert interpret_project_selection("3", choices).status == "invalid"


def test_question_names_candidates():
    prompt = project_selection_question(CATALOG[:2])
    assert "SHAHRUKHZ BY DANUBE" in prompt
    assert "SHAHRUKHZ RESIDENCES BY DANUBE" in prompt
    assert "Both" in prompt


class FakeRedis:
    def __init__(self):
        self.storage = {}

    async def set(self, key, value, ex):
        assert ex > 0
        self.storage[key] = value

    async def get(self, key):
        return self.storage.get(key)

    async def delete(self, key):
        self.storage.pop(key, None)


@pytest.mark.asyncio
async def test_state_is_scoped_and_restores_routing():
    redis = FakeRedis()
    service = ProjectSelectionState(redis)
    route = {"language": "en", "requires_clarification": False, "intents": [
        {"intent": "bank_details", "original_query": "bank account of shahrukhz"}
    ]}
    await service.save(
        user_id="user1", session_id="session1", original_message="bank account of shahrukhz",
        candidates=CATALOG[:2], intent_type="bank_details", routing_result=route,
        intent_index=0,
    )
    assert await service.load(user_id="user1", session_id="session2") is None
    assert await service.load(user_id="user2", session_id="session1") is None
    state = await service.load(user_id="user1", session_id="session1")
    assert state["routing_result"] == route
    assert state["intent_index"] == 0
    await service.clear(user_id="user1", session_id="session1")
    assert await service.load(user_id="user1", session_id="session1") is None

@pytest.mark.asyncio
async def test_sequential_multi_project_queue_state_roundtrip():
    redis = FakeRedis()
    service = ProjectSelectionState(redis)
    route = {
        "language": "en", "requires_clarification": False,
        "intents": [{"intent": "sales_offer", "project_name": None}],
    }
    await service.save(
        user_id="u", session_id="s", original_message="sales offer for shahrukhz",
        candidates=CATALOG[:2], intent_type="sales_offer", routing_result=route,
        intent_index=0, phase="multi_queue", selected_projects=CATALOG[:2],
        queue_position=1,
    )
    state = await service.load(user_id="u", session_id="s")
    assert state["phase"] == "multi_queue"
    assert state["queue_position"] == 1
    assert state["selected_projects"] == CATALOG[:2]


@pytest.mark.asyncio
async def test_shared_availability_parameters_roundtrip():
    redis = FakeRedis()
    service = ProjectSelectionState(redis)
    route = {
        "language": "en", "requires_clarification": False,
        "intents": [{"intent": "download_availability", "currency": "AED", "file_format": None}],
    }
    await service.save(
        user_id="u", session_id="s", original_message="download availability shahrukhz",
        candidates=CATALOG[:2], intent_type="download_availability",
        routing_result=route, intent_index=0, phase="availability_parameters",
        selected_projects=CATALOG[:2],
    )
    state = await service.load(user_id="u", session_id="s")
    assert state["phase"] == "availability_parameters"
    assert state["routing_result"]["intents"][0]["currency"] == "AED"

def test_typo_residences_unique_variant():
    result = match_unique_specific_variant(
        "sharaukhrz residenses",
        CATALOG,
    )

    assert result is not None
    assert result.status == "matched"
    assert result.name == "SHAHRUKHZ RESIDENCES BY DANUBE"


def test_global_matching_typo_residences():
    matches = matching_projects(
        "sharaukhrz residenses",
        CATALOG,
    )

    assert matches == [
        "SHAHRUKHZ RESIDENCES BY DANUBE"
    ]


def test_escrow_message_does_not_ask_for_clarification():
    mentioned, ambiguous = project_mention_candidates(
        "escrow account of sharaukhrz residenses",
        CATALOG,
    )

    assert mentioned is True
    assert ambiguous == []


def test_bank_message_resolves_correct_project():
    result = match_project_in_message(
        "escrow account of sharaukhrz residenses",
        CATALOG,
    )

    assert result.status == "matched"
    assert result.name == "SHAHRUKHZ RESIDENCES BY DANUBE"


def test_router_reference_resolves_correct_project():
    result = match_project_reference(
        "sharaukhrz residenses",
        CATALOG,
    )

    assert result.status == "matched"
    assert result.name == "SHAHRUKHZ RESIDENCES BY DANUBE"


def test_family_only_remains_ambiguous():
    matches = find_project_candidates(
        "shahrukhz",
        CATALOG,
    )

    assert matches == [
        "SHAHRUKHZ BY DANUBE",
        "SHAHRUKHZ RESIDENCES BY DANUBE",
    ]


def test_numbered_projects_are_not_confused():
    assert match_unique_specific_variant(
        "oasiz 1",
        CATALOG,
    ) is None or match_unique_specific_variant(
        "oasiz 1",
        CATALOG,
    ).name == "OASIZ 1 BY DANUBE"

    assert find_project_candidates(
        "oasiz",
        CATALOG,
    ) == [
        "OASIZ 1 BY DANUBE",
        "OASIZ 2 BY DANUBE",
    ]


# --------------------------------------------------
# Dynamic fuzzy project-family regression tests
# --------------------------------------------------

MARKETING_CATALOG = [
    "Shahrukhz",
    "Shahrukhz Residences",
    "BAYZ",
    "BAYZ101",
    "Bayz 102",
    "Greenz",
]


@pytest.mark.parametrize(
    "reference",
    [
        "shahrukz",
        "sharukz",
        "shahrukhz",
        "shahrukh",
    ],
)
def test_fuzzy_shahrukhz_family(reference):
    matches = matching_projects(
        reference,
        MARKETING_CATALOG,
    )

    assert matches == [
        "Shahrukhz",
        "Shahrukhz Residences",
    ]


@pytest.mark.parametrize(
    "reference",
    [
        "bays",
        "bayz",
        "BAYZ",
    ],
)
def test_fuzzy_bayz_family(reference):
    matches = matching_projects(
        reference,
        MARKETING_CATALOG,
    )

    assert matches == [
        "BAYZ",
        "BAYZ101",
        "Bayz 102",
    ]


@pytest.mark.parametrize(
    "message",
    [
        "send me brochure for shahrukz",
        "send me brochure for sharukz",
        "send me brochure for shahrukhz",
    ],
)
def test_marketing_message_requests_family_selection(
    message,
):
    mentioned, candidates = project_mention_candidates(
        message,
        MARKETING_CATALOG,
    )

    assert mentioned is True

    assert candidates == [
        "Shahrukhz",
        "Shahrukhz Residences",
    ]


def test_router_choice_does_not_override_ambiguity():
    # LLM1 might select "Shahrukhz" directly.
    # The original user message must still
    # identify both family candidates.
    message = "send me brochure for shahrukz"

    mentioned, candidates = project_mention_candidates(
        message,
        MARKETING_CATALOG,
    )

    assert mentioned is True
    assert len(candidates) == 2


@pytest.mark.parametrize(
    "reference",
    [
        "Shahrukhz Residences",
        "shahrukz residences",
    ],
)
def test_specific_residences_variant(reference):
    matches = matching_projects(
        reference,
        MARKETING_CATALOG,
    )

    assert matches == ["Shahrukhz Residences"]


def test_complete_project_name_is_unique():
    matches = matching_projects(
        "SHAHRUKHZ BY DANUBE",
        [
            "SHAHRUKHZ BY DANUBE",
            "SHAHRUKHZ RESIDENCES BY DANUBE",
        ],
    )

    assert matches == ["SHAHRUKHZ BY DANUBE"]


def test_numbered_project_is_unique():
    matches = matching_projects(
        "bayz 102",
        MARKETING_CATALOG,
    )

    assert matches == ["Bayz 102"]


def test_unrelated_project_is_not_selected():
    matches = matching_projects(
        "completelyunknown",
        MARKETING_CATALOG,
    )

    assert matches == []


def test_fuzzy_family_clarification_format():
    candidates = matching_projects(
        "shahrukz",
        MARKETING_CATALOG,
    )

    question = project_selection_question(candidates)

    assert "Shahrukhz" in question
    assert "Shahrukhz Residences" in question
    assert "1." in question
    assert "2." in question
