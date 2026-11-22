"""Shared deterministic project ambiguity detection and reply interpretation.

This module never grants access: callers supply service-specific authorized catalogs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.project_name_service import normalize_project_name


@dataclass(frozen=True)
class SelectionResult:
    status: str  # selected | cancelled | invalid
    projects: tuple[str, ...] = ()


def _norm(value: str | None) -> str:
    value = normalize_project_name(str(value or ""))
    return re.sub(r"(?<=[a-z])(?=\d)", " ", value)


def _catalog(catalog) -> list[str]:
    return sorted({
        name.strip() for name in catalog
        if isinstance(name, str) and name.strip()
    })


def matching_projects(reference: str | None, catalog) -> list[str]:
    """All catalog projects consistent with the reference, not a chosen project."""
    names = _catalog(catalog)
    raw = str(reference or "").strip()
    query = _norm(raw)
    if not query or len(query) < 3:
        return []

    # The user's complete official name always uniquely identifies the project.
    explicit_full = [name for name in names if raw.casefold() == name.casefold()]
    if len(explicit_full) == 1:
        return explicit_full

    # A short name is NOT authoritative where other projects share that prefix.
    matches = [
        name for name in names
        if _norm(name) == query
        or _norm(name).startswith(query + " ")
        or (len(query) >= 5 and _norm(name).startswith(query))
    ]

    # An explicit number must never resolve to a differently numbered project.
    numbers = re.findall(r"\b\d+\b", query)
    if numbers:
        matches = [
            name for name in matches
            if re.findall(r"\b\d+\b", _norm(name)) == numbers
        ]
    return matches


def find_project_candidates(reference: str | None, catalog) -> list[str]:
    found = matching_projects(reference, catalog)
    return found if len(found) > 1 else []


def project_mention_candidates(message: str, catalog) -> tuple[bool, list[str]]:
    """Scan actual user wording, overruling an LLM's guessed full name.

    Return (saw_project_mention, ambiguous_matches). The longest identifiable
    span wins, so 'Shahrukhz Residences' is not confused with 'Shahrukhz'.
    """
    names = _catalog(catalog)
    raw = str(message or "")
    if not raw.strip():
        return False, []

    # Complete canonical names in the user's message are authoritative. A
    # request explicitly containing multiple names is for the comparison flow.
    canonical = [
        name for name in names
        if re.search(
            r"(?<![a-z0-9])" + re.escape(name.casefold()) + r"(?![a-z0-9])",
            raw.casefold(),
        )
    ]
    if canonical:
        return True, []

    words = re.findall(r"[a-z0-9]+", raw.casefold())
    best: tuple[int, int, int, list[str]] | None = None
    for start in range(len(words)):
        for end in range(start + 1, min(len(words), start + 6) + 1):
            phrase = " ".join(words[start:end])
            if len(phrase) < 3:
                continue
            candidates = matching_projects(phrase, names)
            if not candidates:
                continue
            # More words and characters = more specific reference. This beats
            # the short prefix 'Shahrukhz' inside 'Shahrukhz Residences'.
            score = (end - start, len(phrase), -start)
            if best is None or score > best[:3]:
                best = (*score, candidates)
    if best is None:
        return False, []
    matches = best[3]
    return True, matches if len(matches) > 1 else []


def interpret_project_selection(reply: str, candidates: list[str]) -> SelectionResult:
    text = _norm(reply)
    if text in {"cancel", "never mind", "nevermind", "stop"}:
        return SelectionResult("cancelled")
    if text in {
        "both", "both projects", "both of them",
        "all", "all projects", "all of them",
    }:
        return SelectionResult("selected", tuple(candidates))
    ordinals = {
        "first": 0, "1st": 0, "first one": 0,
        "second": 1, "2nd": 1, "second one": 1,
        "third": 2, "3rd": 2, "third one": 2,
        "fourth": 3, "4th": 3,
        "fifth": 4, "5th": 4,
        "last": len(candidates) - 1,
    }
    clean = re.sub(r"^(?:option|number|no|choose|select|the)\s+", "", text)
    clean = re.sub(r"\s+one$", "", clean)
    if clean.isdigit():
        index = int(clean) - 1
    else:
        index = ordinals.get(text, ordinals.get(clean))
    if index is not None:
        if 0 <= index < len(candidates):
            return SelectionResult("selected", (candidates[index],))
        return SelectionResult("invalid")
    exact = [name for name in candidates if _norm(name) == text]
    if len(exact) == 1:
        return SelectionResult("selected", (exact[0],))
    if len(text) >= 5:
        matches = [name for name in candidates if _norm(name).startswith(text)]
        if len(matches) == 1:
            return SelectionResult("selected", (matches[0],))
    return SelectionResult("invalid")


def looks_like_project_selection(reply: str) -> bool:
    text = _norm(reply)
    return bool(re.fullmatch(
        r"(?:option |number |select |choose |the )?"
        r"(?:\d{1,2}|first(?: one)?|second(?: one)?|third(?: one)?|"
        r"fourth|fifth|last|both(?: projects)?|all(?: projects)?|"
        r"cancel|stop|never mind|nevermind)",
        text,
    ))



def project_selection_question(
    candidates: list[str],
    allow_both: bool = True,
) -> str:
    options = "\n".join(
        f"{i}. {name}"
        for i, name in enumerate(candidates, 1)
    )

    reply_instruction = (
        "You can reply with the option number, or project name"
    )

    if allow_both:
        reply_instruction += ", or 'Both'"

    return (
        "I found multiple matching projects. "
        "Which project would you like?\n\n"
        f"{options}\n\n"
        f"{reply_instruction}."
    )
