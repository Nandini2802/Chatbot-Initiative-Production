
import re
from difflib import SequenceMatcher

from app.services.project_name_service import normalize_project_name


def _compact(value):
    """Ignore case, spaces, hyphens and underscores."""
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").casefold(),
    )


def _project_aliases(unit):
    """Use project and building names from visible inventory."""
    names = (
        getattr(unit, "project_name", None),
        getattr(unit, "building_name", None),
    )

    return {
        normalize_project_name(name)
        for name in names
        if name
    }


def _resolve_project_name(project_text, units):
    """Resolve against authorized inventory, conservatively handling typos."""
    requested = normalize_project_name(project_text)
    if not requested:
        return None

    aliases = {
        alias
        for unit in units
        for alias in _project_aliases(unit)
        if alias
    }
    if requested in aliases:
        return requested

    # Short inputs are too easy to confuse with unrelated projects.
    if len(_compact(requested)) < 4:
        return None

    ranked = sorted(
        (
            (SequenceMatcher(None, _compact(requested), _compact(alias)).ratio(), alias)
            for alias in aliases
        ),
        reverse=True,
    )
    if not ranked:
        return None

    best_score, best_alias = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score >= 0.80 and best_score - runner_up >= 0.10:
        return best_alias
    return None


def _split_project_reference(reference, units):
    """Parse a project + unit number, allowing confident project typos."""
    parts = str(reference or "").strip().rsplit(maxsplit=1)
    if len(parts) != 2:
        return None

    project_text, unit_number = parts
    project_text = re.sub(
        r"\s+unit(?:\s+(?:no|number))?\.?\s*$",
        "",
        project_text,
        flags=re.IGNORECASE,
    )
    project_name = _resolve_project_name(project_text, units)
    if not project_name or not _compact(unit_number):
        return None
    return project_name, unit_number


def extract_explicit_unit_references(message, units):
    """
    Identify project-unit pairs directly from a comparison message.

    'compare greenz 230 vs aspirz 201'
        -> ['greenz 230', 'aspirz 201']

    Return None if both project-unit pairs cannot be identified.
    """
    text = str(message or "").strip()

    text = re.sub(
        r"^(?:please\s+)?compare\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    references = re.split(
        r"\s+(?:vs\.?|versus|against|with|and|to)\s+|\s*&\s*",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )

    if len(references) != 2:
        return None

    references = [ref.strip() for ref in references]

    if not all(references):
        return None

    if not all(
        _split_project_reference(ref, units) is not None
        for ref in references
    ):
        return None

    return references


def resolve_comparison_unit(
    identifier,
    units,
    project_hint=None,
):
    """
    Resolve one identifier against authorized visible inventory.

    Returns:
        (unit, "matched")
        (None, "not_found")
        (None, "ambiguous")
    """
    units = list(units)

    # An explicit project in an identifier takes priority.
    explicit_reference = _split_project_reference(
        identifier,
        units,
    )

    if explicit_reference:
        project_name, unit_number = explicit_reference

    else:
        # Never silently discard an unrecognized explicit project name.
        # Otherwise "Breezze 4110" might be treated as a bare unit code.
        raw_identifier = str(identifier or "").strip()
        if re.search(r"\s+[^\s]+$", raw_identifier):
            return None, "not_found"
        project_name = (
            _resolve_project_name(project_hint, units)
            if project_hint
            else None
        )
        if project_hint and not project_name:
            return None, "not_found"
        unit_number = raw_identifier

    candidates = units

    if project_name:
        candidates = [
            unit
            for unit in units
            if project_name in _project_aliases(unit)
        ]

    requested = _compact(unit_number)

    if not requested:
        return None, "not_found"

    # Priority 1: Exact full unit name.
    # Example: GRZ-TH-230
    stages = [
        [
            unit for unit in candidates
            if _compact(unit.unit_name) == requested
        ],

        # Priority 2: Exact Unit_Code__c.
        # '201' matches '201', NOT '1201'.
        [
            unit for unit in candidates
            if unit.unit_code is not None
            and _compact(unit.unit_code) == requested
        ],

        # Priority 3: Exact Salesforce unit ID.
        [
            unit for unit in candidates
            if unit.unit_id is not None
            and _compact(unit.unit_id) == requested
        ],

        # Priority 4: Last segment of full unit name.
        # Only for records without a unit code.
        [
            unit for unit in candidates
            if not unit.unit_code
            and unit.unit_name
            and _compact(
                re.split(
                    r"[-_\s]+",
                    str(unit.unit_name).strip(),
                )[-1]
            ) == requested
        ],
    ]

    for matches in stages:
        if len(matches) == 1:
            return matches[0], "matched"

        if len(matches) > 1:
            return None, "ambiguous"

    return None, "not_found"
