
import re
from dataclasses import dataclass

from app.services.project_name_service import normalize_project_name


PROJECT_ALIASES = {
    "aspz": "aspirz",
    "srkz": "shahrukhz",
    "srkr": "shahrukhz residences",
    "elgz": "eleganz",
    "grz": "greenz",
    "dmz": "diamondz",
    "etz": "elitz",
    "etz-2": "elitz 2",
    "etz-3": "elitz 3",
    "fnz": "fashionz",
    "oaz": "oasiz",
    "oaz-1": "oasiz 1",
    "oaz-2": "oasiz 2",
    "ocz": "oceanz",
    "vwz": "viewz",
    "jwz": "jewelz",
    "rszb2": "resortz",
    "b102z": "bayz 102",
    "tmz": "timez",
    "splz": "sparklz",
    "srnz": "serenz",
    "spz": "sportz",
    "brz": "breez",
    "b101z": "bayz 101",
}


@dataclass
class UnitMatch:
    status: str
    units: list


def compact(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").casefold(),
    )


def segments(value):
    return re.findall(
        r"[a-z0-9]+",
        str(value or "").casefold(),
    )


def canonical_project(value):
    name = normalize_project_name(value)
    name = re.sub(r"(?<=[a-z])(?=\d)", " ", name)
    return PROJECT_ALIASES.get(name, name)


def project_matches(unit, project_reference):
    if not project_reference:
        return True

    requested = canonical_project(project_reference)

    names = [
        unit.project_name,
        getattr(unit, "project_code", None),
        getattr(unit, "building_name", None),
    ]

    if unit.unit_name:
        names.append(segments(unit.unit_name)[0])

    for name in names:
        if not name:
            continue

        actual = canonical_project(name)

        if actual == requested:
            return True

        # A family reference can span numbered projects.
        # Keep all matches; never silently choose one.
        if actual.startswith(requested + " "):
            return True

    return False


def split_reference(identifier):
    text = str(identifier or "").strip()

    # Full unit identifiers are handled directly.
    if "-" in text or "_" in text:
        return None, text

    # "Serenz retail 01"
    match = re.fullmatch(
        r"(.+?)\s+(retail|shop|restaurant)\s+(\d+[a-z]?)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return (
            match.group(1),
            f"{match.group(2)} {match.group(3)}",
        )

    # "Serenz 101"
    match = re.fullmatch(
        r"(.+?)\s+(?:unit\s+)?(\d+[a-z]?)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1), match.group(2)

    return None, text


def unique_units(units):
    found = {}

    for unit in units:
        if unit.unit_id:
            found[str(unit.unit_id)] = unit

    return sorted(
        found.values(),
        key=lambda u: (
            str(u.project_name or "").casefold(),
            str(u.unit_name or "").casefold(),
            str(u.unit_id),
        ),
    )


def resolve_units(identifier, units, project_hint=None):
    """
    Returns:
      matched   -> one uniquely identified unit
      ambiguous -> multiple authorized matches
      not_found -> no authorized match

    Never guesses a tower or chooses the first match.
    """

    identifier = str(identifier or "").strip()

    if not identifier:
        return UnitMatch("not_found", [])

    units = [u for u in units if u.unit_id]
    requested = compact(identifier)

    # 1. Exact Salesforce ID or full unit name.
    direct = unique_units([
        u for u in units
        if any(
            compact(value) == requested
            for value in (u.unit_id, u.unit_name)
            if value
        )
    ])

    if direct:
        return UnitMatch(
            "matched" if len(direct) == 1 else "ambiguous",
            direct,
        )

    explicit_project, unit_reference = split_reference(identifier)

    project_reference = explicit_project or project_hint

    if project_reference:
        units = [
            u for u in units
            if project_matches(u, project_reference)
        ]

    if not units:
        return UnitMatch("not_found", [])

    requested = compact(unit_reference)
    requested_parts = segments(unit_reference)

    # 2. Exact Unit_Code__c, such as 101 or 1114.
    code_matches = unique_units([
        u for u in units
        if u.unit_code
        and compact(u.unit_code) == requested
    ])

    if code_matches:
        return UnitMatch(
            "matched" if len(code_matches) == 1 else "ambiguous",
            code_matches,
        )

    # 3. Complete trailing identifier segments.
    # 101 must not match 1101 or 1010.
    suffix_matches = []

    for unit in units:
        parts = segments(unit.unit_name)

        if not parts or not requested_parts:
            continue

        if (
            len(requested_parts) <= len(parts)
            and parts[-len(requested_parts):] == requested_parts
        ):
            suffix_matches.append(unit)

    suffix_matches = unique_units(suffix_matches)

    if suffix_matches:
        return UnitMatch(
            "matched" if len(suffix_matches) == 1 else "ambiguous",
            suffix_matches,
        )

    return UnitMatch("not_found", [])


def select_candidate(message, candidates):
    """
    Select only from the pending authorized candidates.

    Supports:
      Tower A / Tower B
      Building A
      First one / Second one
      Option 1 / Option 2
      Full unit name or ID
      Floor F01
    """

    text = str(message or "").strip().casefold()
    candidates = unique_units(candidates)

    if not candidates:
        return UnitMatch("not_found", [])

    ordinal_names = {
        "first": 0,
        "second": 1,
        "third": 2,
        "fourth": 3,
        "fifth": 4,
        "sixth": 5,
        "seventh": 6,
        "eighth": 7,
        "ninth": 8,
        "tenth": 9,
    }

    ordinal_match = re.fullmatch(
        r"(?:the\s+)?"
        r"(first|second|third|fourth|fifth|sixth|"
        r"seventh|eighth|ninth|tenth)"
        r"(?:\s+(?:one|unit))?",
        text,
    )

    if ordinal_match:
        index = ordinal_names[ordinal_match.group(1)]
        if index < len(candidates):
            return UnitMatch("matched", [candidates[index]])

    option_match = re.fullmatch(
        r"(?:option|number|no\.?)\s*#?\s*(\d+)",
        text,
    )

    if option_match:
        index = int(option_match.group(1)) - 1
        if 0 <= index < len(candidates):
            return UnitMatch("matched", [candidates[index]])

    # Full name, unit code, or Salesforce ID.
    direct = resolve_units(text, candidates)

    if direct.status != "not_found":
        return direct

    # Allow "unit SRNZ-B-F01-101".
    cleaned = re.sub(
        r"^(?:select|choose|unit|the unit)\s+",
        "",
        text,
    ).strip()

    if cleaned != text:
        direct = resolve_units(cleaned, candidates)

        if direct.status != "not_found":
            return direct

    tower_match = re.fullmatch(
        r"(?:tower|building|block)\s+([a-z0-9]+)",
        text,
    )

    if tower_match:
        tower = tower_match.group(1)

        matches = []

        for unit in candidates:
            parts = segments(unit.unit_name)
            building = compact(
                getattr(unit, "building_code", None)
            )

            # Restrict to a complete tower segment.
            if (
                building == tower
                or tower in parts[1:-1]
            ):
                matches.append(unit)

        matches = unique_units(matches)

        return UnitMatch(
            "matched" if len(matches) == 1
            else "ambiguous" if matches
            else "not_found",
            matches,
        )

    floor_match = re.fullmatch(
        r"(?:floor)\s+(f?\d+)",
        text,
    )

    if floor_match:
        floor = compact(floor_match.group(1))

        matches = [
            u for u in candidates
            if any(
                compact(part) in {floor, "f" + floor}
                for part in segments(u.unit_name)
            )
        ]

        matches = unique_units(matches)

        return UnitMatch(
            "matched" if len(matches) == 1
            else "ambiguous" if matches
            else "not_found",
            matches,
        )

    return UnitMatch("not_found", [])


def format_unit_choices(units, reference=None):
    units = unique_units(units)

    heading = (
        f"I found {len(units)} matching units"
        + (f" for {reference}" if reference else "")
        + ". Which one are you referring to?"
    )

    lines = [
        f"{index}. {unit.unit_name or unit.unit_id}"
        for index, unit in enumerate(units[:20], start=1)
    ]

    if len(units) > 20:
        lines.append(
            f"And {len(units) - 20} more. "
            "Please enter the full unit name."
        )

    return (
        heading
        + "\n\n"
        + "\n".join(lines)
        + "\n\nPlease reply with the full unit name, "
          "tower, or option number."
    )


def is_specific_unit_intent(intent):
    if intent.intent == "sales_offer":
        return True

    return (
        intent.intent == "inventory"
        and intent.inventory_operation in {
            "payment_plan",
            "unit_details",
            "unit_layout_plan",
            "unit_comparison",
        }
    )


def get_unit_references(intent, original_message):
    """
    Returns (slot_index, reference) pairs.

    slot_index=None for a single-unit operation.
    slot_index=0 or 1 for comparison.
    """

    if not is_specific_unit_intent(intent):
        return []

    if intent.inventory_operation == "unit_comparison":
        references = list(intent.compare_unit_numbers or [])

        # Recover explicit comparisons if the router missed
        # the two project-unit expressions.
        if len(references) != 2:
            match = re.fullmatch(
                r"(?:please\s+)?compare\s+(.+?)\s+"
                r"(?:vs\.?|versus|against|with|and)\s+(.+)",
                original_message.strip(),
                flags=re.IGNORECASE,
            )

            if match:
                references = [
                    match.group(1).strip(),
                    match.group(2).strip(),
                ]

        if len(references) != 2:
            return []

        return list(enumerate(references))

    reference = (
        getattr(intent, "unit_id", None)
        or getattr(intent, "unit_name", None)
        or getattr(intent, "unit_number", None)
    )

    if not reference:
        # Recover "sales offer of sernz 101" or
        # "payment plan for sernz 101".
        match = re.search(
            r"\b(?:sales\s+offer|payment\s+plan|"
            r"unit\s+details|details|layout\s+plan|"
            r"floor\s+plan|unit\s+layout)"
            r"\s+(?:for|of)\s+(.+?)\s*$",
            original_message,
            flags=re.IGNORECASE,
        )

        if match:
            candidate = match.group(1).strip()

            if re.search(r"\d", candidate):
                reference = candidate

    return [(None, reference)] if reference else []


def apply_selected_unit(intent, unit, slot_index=None):
    """
    Adapt the resolved unit to existing handler contracts.
    """

    if (
        intent.intent == "inventory"
        and intent.inventory_operation == "unit_comparison"
    ):
        references = list(intent.compare_unit_numbers or [])

        if len(references) != 2 or slot_index is None:
            raise ValueError(
                "Comparison requires two unit references."
            )

        references[slot_index] = (
            unit.unit_name or str(unit.unit_id)
        )
        intent.compare_unit_numbers = references
        intent.project_name = None

        resolved_fields = {
            "compare_unit_numbers",
            "unit_identifier",
            "project_name",
            "project_identifier",
        }

    else:
        # Existing handlers can identify the Salesforce ID.
        intent.unit_id = str(unit.unit_id)
        intent.unit_number = str(unit.unit_id)
        intent.unit_name = unit.unit_name

        # Prevent a stale/router-guessed project filter
        # from rejecting a verified authorized unit.
        intent.project_id = None
        intent.project_name = None
        intent.project_number = None
        intent.explicit_project_reference = None
        intent.project_reference_source = "none"

        resolved_fields = {
            "unit_id",
            "unit_name",
            "unit_number",
            "unit_identifier",
            "project_name",
            "project_identifier",
            "project_or_unit_identifier",
        }

    intent.missing_fields = [
        field
        for field in intent.missing_fields
        if field not in resolved_fields
    ]

    intent.requires_clarification = bool(
        intent.missing_fields
    )


def looks_like_unit_selection(message):
    text = str(message or "").strip().casefold()

    if re.fullmatch(
        r"(?:tower|building|block|floor)\s+[a-z0-9]+",
        text,
    ):
        return True

    if re.fullmatch(
        r"(?:option|number|no\.?)\s*#?\s*\d+",
        text,
    ):
        return True

    if text in {
        "first", "second", "third", "fourth", "fifth",
        "first one", "second one", "third one",
        "fourth one", "fifth one",
    }:
        return True

    if re.fullmatch(
        r"(?:unit\s+)?[a-z0-9]+"
        r"(?:[-_][a-z0-9]+)+",
        text,
    ):
        return True

    return False

