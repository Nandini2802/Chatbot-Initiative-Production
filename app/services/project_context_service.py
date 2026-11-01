
from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, Literal

from app.services.project_resolution_service import (
    match_project_in_message,
    match_project_reference,
)
from app.services.project_name_service import (
    normalize_project_name,
)


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


def resolve_session_project(
    *,
    message: str,
    router_project: str | None,
    active_project: str | None,
    allowed_projects: Collection[str],
    project_reference_source: ProjectSource = "none",
    explicit_project_reference: str | None = None,
    inherit: bool = True,
) -> ContextDecision:

    # 1. Independently inspect the current message.
    current_match = match_project_in_message(
        message,
        allowed_projects,
    )

    if current_match.status == "ambiguous":
        return ContextDecision(
            status="ambiguous",
            source="message",
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
