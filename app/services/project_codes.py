"""
Short project codes (GRZ, DMZ, ETZ-2, ...) from the Units API.

Each unit returned by GetAllUnitsVisibleToBroker carries its project's
code (ProjectCode__c -> unit.project_code). The lookup is built per
request from the user's own units, so it is always current and only
contains projects the user can see.

  - unique code        -> that project            ("GRZ" -> GREENZ BY DANUBE)
  - shared code        -> several projects         ("ELGZ" -> ELEGANZ 2, ELEGANZ 5)
  - code inside a unit -> ignored ("GRZ-TH-188" is a unit, not the project code)
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from app.services.project_name_service import normalize_project_name


logger = logging.getLogger(__name__)

MIN_CODE_LENGTH = 2


def _code_key(code: str) -> str:
    """'etz 2', 'ETZ_2', 'etz-2' -> 'ETZ-2'."""
    return "-".join(
        part for part in re.split(r"[\s_\-]+", str(code or "").strip().upper()) if part
    )


def build_project_code_map(
    units: Iterable,
    project_names: Iterable[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    """
    code -> official project name(s), from the user's units.

    A code is dropped when it is the same text as another project's
    name (so a code can never shadow a project name).
    """

    codes: dict[str, list[str]] = {}

    for unit in units or ():
        code = _code_key(getattr(unit, "project_code", None))
        project = str(getattr(unit, "project_name", "") or "").strip()

        if len(code.replace("-", "")) < MIN_CODE_LENGTH or not project:
            continue

        names = codes.setdefault(code, [])

        if project not in names:
            names.append(project)

    known_names = {
        normalize_project_name(name)
        for name in (project_names or ())
        if name
    }

    result = {}

    for code, names in codes.items():
        code_as_name = normalize_project_name(code)
        own = {normalize_project_name(name) for name in names}

        if code_as_name in known_names and code_as_name not in own:
            continue

        result[code] = tuple(sorted(names))

    return result


def _code_pattern(code: str) -> re.Pattern:
    """
    Standalone code, separators optional between parts ("ETZ-2", "etz 2",
    "etz2"). Not part of a longer word, and not followed by "-<letters or
    digits>" (that would be a unit name such as GRZ-TH-188).
    """
    parts = [re.escape(part.lower()) for part in code.split("-")]
    body = r"[\s_\-]?".join(parts)
    return re.compile(
        r"(?<![a-z0-9\-])" + body + r"(?![a-z0-9]|[\-_][a-z0-9])"
    )


def find_project_codes(
    text: str | None,
    code_map: dict[str, tuple[str, ...]] | None,
) -> tuple[str, ...]:
    """
    Projects referred to by codes in the text, in code order.
    Longer codes are matched first ("ETZ-2" before "ETZ").
    """

    if not text or not code_map:
        return ()

    remaining = str(text).casefold()
    projects: list[str] = []

    for code in sorted(code_map, key=len, reverse=True):
        pattern = _code_pattern(code)

        if not pattern.search(remaining):
            continue

        # Remove the match so a shorter code cannot match inside it.
        remaining = pattern.sub(" ", remaining)

        for name in code_map[code]:
            if name not in projects:
                projects.append(name)

    return tuple(projects)


def codes_in_project_reference(
    text: str | None,
    code_map: dict[str, tuple[str, ...]] | None,
) -> tuple[str, ...]:
    """
    Projects for a short project reference ("GRZ", "GRZ in AED").

    Stricter than find_project_codes: nothing else in the text may
    contain a digit, so unit references ("grz th 188") are left alone.
    """

    if not text or not code_map:
        return ()

    remaining = str(text).casefold()
    projects: list[str] = []

    for code in sorted(code_map, key=len, reverse=True):
        pattern = _code_pattern(code)

        if pattern.search(remaining):
            remaining = pattern.sub(" ", remaining)

            for name in code_map[code]:
                if name not in projects:
                    projects.append(name)

    if not projects or re.search(r"\d", remaining):
        return ()

    return tuple(projects)


def router_code_context(
    code_map: dict[str, tuple[str, ...]] | None,
) -> dict[str, str | list[str]]:
    """Codes for the router prompt: one name, or a list when shared."""

    return {
        code: names[0] if len(names) == 1 else list(names)
        for code, names in sorted((code_map or {}).items())
    }
