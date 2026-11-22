
import re
from dataclasses import dataclass

from app.services.project_name_service import (
    normalize_project_name,
)


@dataclass(frozen=True)
class SelectionResult:
    status: str
    projects: tuple[str, ...] = ()


def _norm(value: str | None) -> str:
    text = normalize_project_name(value)
    return re.sub(r"(?<=[a-z])(?=\d)", " ", text)


def find_project_candidates(
    reference: str | None,
    catalog: list[str],
) -> list[str]:
    query = _norm(reference)

    if not query:
        return []

    names = sorted({
        name.strip()
        for name in catalog
        if isinstance(name, str) and name.strip()
    })

    # Explicit full canonical name.
    full = [
        name for name in names
        if str(reference).strip().casefold()
        == name.casefold()
    ]

    if len(full) == 1:
        return []

    # The reference must be a complete project
    # prefix, not an arbitrary substring.
    candidates = [
        name for name in names
        if (
            _norm(name) == query
            or _norm(name).startswith(query + " ")
            or (
                len(query) >= 5
                and _norm(name).startswith(query)
            )
        )
    ]

    # Never confuse explicitly numbered projects.
    numbers = re.findall(r"\b\d+\b", query)

    if numbers:
        candidates = [
            name for name in candidates
            if re.findall(
                r"\b\d+\b",
                _norm(name),
            ) == numbers
        ]

    return candidates if len(candidates) > 1 else []


def interpret_project_selection(
    reply: str,
    candidates: list[str],
) -> SelectionResult:
    text = _norm(reply)

    if text in {"cancel", "never mind", "nevermind"}:
        return SelectionResult("cancelled")

    if text in {
        "both",
        "both projects",
        "both of them",
        "all",
        "all projects",
        "all of them",
    }:
        return SelectionResult(
            "selected",
            tuple(candidates),
        )

    if text.isdigit():
        index = int(text) - 1

        if 0 <= index < len(candidates):
            return SelectionResult(
                "selected",
                (candidates[index],),
            )

        return SelectionResult("invalid")

    exact = [
        name for name in candidates
        if _norm(name) == text
    ]

    if len(exact) == 1:
        return SelectionResult(
            "selected",
            (exact[0],),
        )

    # A unique, sufficiently specific name prefix.
    if len(text) >= 5:
        matches = [
            name for name in candidates
            if _norm(name).startswith(text + " ")
        ]

        if len(matches) == 1:
            return SelectionResult(
                "selected",
                (matches[0],),
            )

    return SelectionResult("invalid")


def project_selection_question(
    candidates: list[str],
) -> str:
    options = "\n".join(
        f"{i}. {name}"
        for i, name in enumerate(candidates, 1)
    )

    return (
        "I found multiple matching projects. "
        "Which project would you like?\n\n"
        f"{options}\n\n"
        "You can reply with the option number, "
        "project name, or 'Both'."
    )
