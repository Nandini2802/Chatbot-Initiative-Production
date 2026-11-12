
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Collection, Literal

from app.services.project_resolution_service import (
    match_project_in_message,
    match_project_reference,
)
from app.services.project_name_service import (
    normalize_project_name,
)
from app.services.project_codes import find_project_codes
from app.services.project_resolution_service import ProjectResolution


logger = logging.getLogger(__name__)


def _numbers(value: str | None) -> list[str]:
    return re.findall(r"\d+", normalize_project_name(value))


def _family(value: str | None) -> str:
    """Project name without its numbers: 'ELEGANZ 2 BY DANUBE' -> 'eleganz'."""
    return " ".join(
        word
        for word in normalize_project_name(value).split()
        if not word.isdigit()
    )


def router_tiebreak(
    *,
    message: str,
    router_project: str | None,
    candidates,
) -> str | None:
    """
    Resolve an ambiguous message using the router's project choice.

    The router picks project names from the same fixed project lists
    the backend uses. Its choice is accepted only when:
      - it is exactly one of the ambiguous candidates found in the
        user's own message (so it can never introduce another project);
      - it is not a numbered-family guess: when another candidate is the
        same project family with a different number (ELEGANZ 2 / 5), the
        user must have typed that project's number.

    Returns the chosen official project name, or None to keep asking.
    """

    if not router_project or not candidates:
        return None

    key = normalize_project_name(router_project)

    chosen = [
        name for name in candidates
        if normalize_project_name(name) == key
    ]

    if len(chosen) != 1:
        return None

    choice = chosen[0]

    same_family_conflict = any(
        name != choice and _family(name) == _family(choice)
        for name in candidates
    )

    if same_family_conflict:
        message_numbers = set(
            re.findall(r"\d+", str(message or ""))
        )
        required = _numbers(choice)

        if not required or not set(required) <= message_numbers:
            return None

    return choice


ProjectSource = Literal[
    "explicit",
    "context",
    "none",
    "uncertain",
]


@dataclass(frozen=True)
class ContextDecision:
    status: str
    project_name: str | None = None
    source: str | None = None
    should_update_session: bool = False
    # Matching projects when status == "ambiguous".
    candidates: tuple[str, ...] = ()


MAX_CLARIFICATION_CANDIDATES = 5


def format_ambiguous_project_clarification(
    candidates,
) -> str | None:
    """
    Ask the user to choose between ambiguous projects.

    Returns None when there are fewer than two distinct
    candidates, so callers keep their existing message.
    """

    names = list(dict.fromkeys(
        str(name).strip()
        for name in (candidates or ())
        if name and str(name).strip()
    ))[:MAX_CLARIFICATION_CANDIDATES]

    if len(names) < 2:
        return None

    if len(names) == 2:
        options = f"{names[0]} or {names[1]}"
    else:
        options = (
            ", ".join(names[:-1])
            + f" or {names[-1]}"
        )

    return (
        "I found more than one matching project. "
        f"Did you mean {options}?"
    )


def resolve_session_project(
    *,
    message: str,
    router_project: str | None,
    active_project: str | None,
    allowed_projects: Collection[str],
    project_reference_source: ProjectSource = "none",
    explicit_project_reference: str | None = None,
    inherit: bool = True,
    allow_router_tiebreak: bool = True,
    project_codes: dict | None = None,
) -> ContextDecision:

    # 1. Independently inspect the current message.
    current_match = match_project_in_message(
        message,
        allowed_projects,
    )

    # 1b. No project name in the message: look for a short project
    # code from the user's Units API data ("sales offer for GRZ").
    if current_match.status == "not_found" and project_codes:
        allowed_keys = {
            normalize_project_name(name): name
            for name in allowed_projects
        }

        coded = [
            allowed_keys[normalize_project_name(name)]
            for name in find_project_codes(message, project_codes)
            if normalize_project_name(name) in allowed_keys
        ]

        if len(coded) == 1:
            logger.info(
                "PROJECT_CODE_MATCH | project=%s",
                coded[0],
            )

            return ContextDecision(
                status="matched",
                project_name=coded[0],
                source="explicit",
                should_update_session=True,
            )

        if len(coded) > 1:
            # Shared code (e.g. ELGZ): same handling as an
            # ambiguous name below.
            current_match = ProjectResolution(
                "ambiguous",
                candidates=tuple(coded),
            )

    if current_match.status == "ambiguous":

        # 1a. The user named a project explicitly and the router chose
        # one of the candidates from the official list: use it.
        if (
            allow_router_tiebreak
            and project_reference_source == "explicit"
        ):
            choice = router_tiebreak(
                message=message,
                router_project=router_project,
                candidates=current_match.candidates,
            )

            if choice:
                logger.info(
                    "PROJECT_ROUTER_TIEBREAK | chosen=%s | "
                    "candidates=%s",
                    choice,
                    list(current_match.candidates),
                )

                return ContextDecision(
                    status="matched",
                    project_name=choice,
                    source="explicit",
                    should_update_session=True,
                )

        return ContextDecision(
            status="ambiguous",
            source="message",
            candidates=current_match.candidates,
        )

    # 2. The router reports an explicit project.
    if project_reference_source == "explicit":

        reference = (
            explicit_project_reference or ""
        ).strip()

        # Missing explicit phrase is not permission
        # to inherit the previous project.
        if not reference:
            return ContextDecision(
                status="unresolved_explicit",
                source="router",
            )

        # Prefer an independently verified match
        # from the current user message.
        if current_match.status == "matched":
            reference_match = match_project_reference(
                reference,
                allowed_projects,
            )

            if (
                reference_match.status == "matched"
                and normalize_project_name(
                    reference_match.name
                ) == normalize_project_name(
                    current_match.name
                )
            ):
                return ContextDecision(
                    status="matched",
                    project_name=current_match.name,
                    source="explicit",
                    should_update_session=True,
                )

            # Disagreement between router extraction
            # and message matching is unsafe.
            return ContextDecision(
                status="unresolved_explicit",
                source="conflict",
            )

        # Try resolving the explicitly extracted
        # phrase against the official catalog.
        reference_match = match_project_reference(
            reference,
            allowed_projects,
        )

        if reference_match.status == "matched":
            return ContextDecision(
                status="matched",
                project_name=reference_match.name,
                source="explicit",
                should_update_session=True,
            )

        if reference_match.status == "ambiguous":
            return ContextDecision(
                status="ambiguous",
                source="explicit",
                candidates=reference_match.candidates,
            )

        return ContextDecision(
            status="unresolved_explicit",
            source="explicit",
        )

    # 3. A project independently detected in the
    # current message takes priority over history.
    if current_match.status == "matched":
        return ContextDecision(
            status="matched",
            project_name=current_match.name,
            source="explicit",
            should_update_session=True,
        )

    # 4. An uncertain new reference must not
    # silently fall back to the old project.
    if project_reference_source == "uncertain":
        return ContextDecision(
            status="unresolved_explicit",
            source="uncertain",
        )

    # 5. Inherit the existing session project.
    if inherit and active_project:

        inherited = match_project_reference(
            active_project,
            allowed_projects,
        )

        if inherited.status == "matched":
            return ContextDecision(
                status="matched",
                project_name=inherited.name,
                source="session",
                should_update_session=False,
            )

        if inherited.status == "ambiguous":
            return ContextDecision(
                status="ambiguous",
                source="session",
                candidates=inherited.candidates,
            )

    # 6. Router fallback only when there is no
    # saved project and the router explicitly
    # identifies a contextual project.
    if (
        router_project
        and project_reference_source == "context"
    ):
        routed = match_project_reference(
            router_project,
            allowed_projects,
        )

        if routed.status == "matched":
            return ContextDecision(
                status="matched",
                project_name=routed.name,
                source="router_context",
                should_update_session=False,
            )

        if routed.status == "ambiguous":
            return ContextDecision(
                status="ambiguous",
                source="router_context",
                candidates=routed.candidates,
            )

    return ContextDecision(
        status="not_found",
    )


def same_project(
    first: str | None,
    second: str | None,
) -> bool:
    return (
        bool(first)
        and bool(second)
        and normalize_project_name(first)
        == normalize_project_name(second)
    )
