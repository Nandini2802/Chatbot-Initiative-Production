
import re

from rapidfuzz.distance import OSA

from app.services.sales_offer_resolver import (
    find_unit,
    SalesOfferResolutionError,
)


# --------------------------------------------------------------------------
# Typo-tolerant unit matching (used only as a fallback, after the existing
# exact / ordinal / partial rules have found nothing).
# --------------------------------------------------------------------------

# Words that can surround a unit reference in a selection reply,
# e.g. "the 188 one", "I want grz th 188 please".
SELECTION_FILLER_WORDS = {
    "a", "an", "the", "this", "that", "it", "is",
    "one", "unit", "number", "no", "please", "pls",
    "i", "want", "need", "would", "like", "take", "go", "with",
    "select", "choose", "pick", "give", "me", "for",
    "ok", "okay", "lets", "let's",
}

MAX_UNIT_SUGGESTIONS = 5
MIN_TYPO_KEY_LENGTH = 5


def compact_unit_key(value) -> str:
    """
    Formatting-insensitive key for a unit name.

    Ignores case, spaces, dashes, underscores and other separators,
    and leading zeros in each number:
        "GRZ-TH-188", "grz th 188", "GRZ_TH_0188" -> "grzth188"
    """
    text = str(value or "").casefold()
    parts = re.findall(r"[a-z]+|\d+", text)

    return "".join(
        (part.lstrip("0") or "0") if part.isdigit() else part
        for part in parts
    )


def _unit_keys(unit):
    keys = set()

    for value in (unit.unit_name, unit.unit_code):
        key = compact_unit_key(value)

        if key:
            keys.add(key)

    return keys


def find_compact_unit_match(text, units):
    """
    Unit whose name differs from the text only by formatting
    (case, separators, leading zeros). None unless exactly one.
    """
    key = compact_unit_key(text)

    if not key:
        return None

    matches = {
        unit.unit_id: unit
        for unit in units
        if unit.unit_id and key in _unit_keys(unit)
    }

    return next(iter(matches.values())) if len(matches) == 1 else None


def find_typo_unit_candidates(text, units):
    """
    Units exactly one edit away from the text (one wrong, missing or
    extra character, or two neighbouring characters swapped), after
    formatting is ignored.

    Applies only to identifier-like text (letters and digits, at least
    MIN_TYPO_KEY_LENGTH characters) so short or plain-number input never
    produces guesses. Returns units in their original order.
    """
    key = compact_unit_key(text)

    if (
        len(key) < MIN_TYPO_KEY_LENGTH
        or not re.search(r"[a-z]", key)
        or not re.search(r"\d", key)
    ):
        return []

    candidates = []
    seen = set()

    for unit in units:
        if not unit.unit_id or unit.unit_id in seen:
            continue

        if any(
            OSA.distance(key, unit_key) == 1
            for unit_key in _unit_keys(unit)
        ):
            candidates.append(unit)
            seen.add(unit.unit_id)

    return candidates


MAX_REFERENCE_WORDS = 3


def single_unit_reference(message: str):
    """
    The unit reference in a short selection reply, with filler words
    removed ("the 188 one" -> "188", "I want grz th 188 please" ->
    "grz th 188"). None when nothing or more than MAX_REFERENCE_WORDS
    words remain.

    The result is only ever compared against the offered units, so
    ordinary requests ("units under 200") never match a unit.
    """
    words = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", message.casefold())

    remaining = [
        word for word in words
        if word not in SELECTION_FILLER_WORDS
    ]

    if not 1 <= len(remaining) <= MAX_REFERENCE_WORDS:
        return None

    return " ".join(remaining)


def typo_suggestion_result(text, units, allowed_ids, snapshot):
    """
    Typo fallback:
      - exactly one close unit -> (unit, True): asks "Are you referring to...?"
      - 2..MAX close units      -> raises with "Did you mean A, B or C?"
      - none / too many         -> None (caller keeps its existing behaviour)
    """
    candidates = find_typo_unit_candidates(text, units)

    if len(candidates) == 1:
        unit, _ = find_unit(
            candidates[0].unit_id,
            snapshot,
            allowed_unit_ids=allowed_ids,
        )
        return unit, True

    if 2 <= len(candidates) <= MAX_UNIT_SUGGESTIONS:
        names = [unit.unit_name or unit.unit_id for unit in candidates]
        options = (
            f"{names[0]} or {names[1]}"
            if len(names) == 2
            else ", ".join(names[:-1]) + f" or {names[-1]}"
        )

        raise SalesOfferResolutionError(
            f"I found close matches: {options}. "
            "Which unit did you mean?"
        )

    return None


ORDINALS = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "4th": 3,
    "fifth": 4,
    "5th": 4,
    "sixth": 5,
    "6th": 5,
    "seventh": 6,
    "7th": 6,
    "eighth": 7,
    "8th": 7,
    "ninth": 8,
    "9th": 8,
    "tenth": 9,
    "10th": 9,
    "last": -1,
}


def extract_ordinal(message: str):
    text = message.strip().casefold()

    match = re.fullmatch(
        r"(?:"
        r"(?:i\s+want|give\s+me|select|choose|"
        r"pick|for|this\s+is|what\s+about)\s+"
        r"(?:the\s+)?"
        r")?"
        r"(first|1st|second|2nd|third|3rd|"
        r"fourth|4th|fifth|5th|sixth|6th|"
        r"seventh|7th|eighth|8th|ninth|9th|"
        r"tenth|10th|last)"
        r"(?:\s+(?:one|unit))?",
        text,
    )

    if match:
        return ORDINALS[match.group(1)]

    numeric = re.fullmatch(
        r"(?:unit|option|number|no\.?)\s*#?\s*(\d+)",
        text,
    )

    if numeric:
        return int(numeric.group(1)) - 1

    return None


def extract_unit_reference(message: str, units):
    """
    Match a complete authorized unit identifier
    anywhere in the message.

    Do not guess when multiple units are mentioned.
    """
    text = message.casefold()
    matched = set()

    for unit in units:
        if not unit.unit_id:
            continue

        for value in (
            unit.unit_id,
            unit.unit_name,
            unit.unit_code,
        ):
            if not value:
                continue

            value = str(value).strip()

            if len(value) < 4:
                continue

            pattern = (
                r"(?<![a-z0-9])"
                + re.escape(value.casefold())
                + r"(?![a-z0-9])"
            )

            if re.search(pattern, text):
                matched.add(unit.unit_id)

    if len(matched) == 1:
        return next(iter(matched))

    return None


def extract_partial_unit_reference(message: str, units):
    """
    Additional matching for partial unit references.

    Example: ASPZ-F02-11013
    Accepts:
      - aspz 11013 unit
      - F02
      - 11013
      - unit 11013
      - select F02

    Matches complete identifier segments only.
    Searches only the supplied authorized units.
    """

    text = message.strip().casefold()

    # Remove common selection phrases.
    text = re.sub(
        r"^(?:this one|select|choose|pick|"
        r"unit number|unit|number)\s+",
        "",
        text,
    )

    text = re.sub(
        r"\s+unit$",
        "",
        text,
    ).strip()

    # Only accept identifier-like input.
    if not re.fullmatch(r"[a-z0-9_-]+(?:\s+[a-z0-9_-]+)*", text):
        return None

    requested_parts = re.findall(r"[a-z0-9]+", text)

    if not requested_parts:
        return None

    matches = {}

    for unit in units:
        if not unit.unit_id:
            continue

        for value in (unit.unit_name, unit.unit_code):
            if not value:
                continue

            unit_parts = re.findall(
                r"[a-z0-9]+",
                str(value).casefold(),
            )

            if all(
                part in unit_parts
                for part in requested_parts
            ):
                matches[unit.unit_id] = unit
                break

    if len(matches) == 1:
        return next(iter(matches))

    if len(matches) > 1:
        raise SalesOfferResolutionError(
            "Multiple units match your reference. "
            "Please provide a more specific unit number "
            "or the complete unit name."
        )

    return None


def resolve_sales_offer_selection(
    message: str,
    pending: dict,
    snapshot,
):
    """
    Returns:
        (unit, needs_confirmation)
        or None if this is not a recognizable selection.

    Uses only units in the pending Sales Offer.
    """

    if pending.get("stage") != "unit_selection":
        return None

    allowed_ids = pending.get("candidate_unit_ids", [])
    allowed_set = set(allowed_ids)

    units = [
        unit
        for unit in snapshot.units
        if unit.unit_id in allowed_set
    ]

    displayed_ids = pending.get(
        "displayed_unit_ids", []
    )

    if re.fullmatch(
        r"(?:unit|unit number)\s+\d{3,}",
        message.strip(),
        flags=re.IGNORECASE,
    ):
        partial_id = extract_partial_unit_reference(
            message,
            units,
        )

        if partial_id:
            unit, _ = find_unit(
                partial_id,
                snapshot,
                allowed_unit_ids=allowed_ids,
            )
            return unit, True

        return None

    ordinal = extract_ordinal(message)

    if ordinal is not None:
        if not displayed_ids:
            raise SalesOfferResolutionError(
                "The displayed unit order is unavailable. "
                "Please select a unit by its name or ID."
            )

        try:
            selected_id = displayed_ids[ordinal]
        except IndexError:
            raise SalesOfferResolutionError(
                "That unit number is not in the "
                "displayed listing."
            )

        return find_unit(
            selected_id,
            snapshot,
            allowed_unit_ids=allowed_ids,
        )

    matched_id = extract_unit_reference(
        message,
        units,
    )

    if matched_id:
        return find_unit(
            matched_id,
            snapshot,
            allowed_unit_ids=allowed_ids,
        )

    # Formatting-only differences ("grz th 188", "GRZ_TH_188",
    # "grz-th-0188") identify exactly one unit: no confirmation.
    compact_unit = find_compact_unit_match(
        message.strip(),
        units,
    )

    if compact_unit:
        return find_unit(
            compact_unit.unit_id,
            snapshot,
            allowed_unit_ids=allowed_ids,
        )

    # Existing resolver supports normalized identifiers.
    # Only attempt this for a standalone unit reference.
    value = message.strip()

    if re.fullmatch(
        r"[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)+",
        value,
    ):
        try:
            return find_unit(
                value,
                snapshot,
                allowed_unit_ids=allowed_ids,
            )

        except SalesOfferResolutionError:
            # Not found: offer the unit(s) one typo away,
            # otherwise keep the existing "not found" error.
            suggestion = typo_suggestion_result(
                value, units, allowed_ids, snapshot,
            )

            if suggestion:
                return suggestion

            raise

    partial_matched_id = extract_partial_unit_reference(
        message,
        units,
    )

    if partial_matched_id:
        unit, _ = find_unit(
            partial_matched_id,
            snapshot,
            allowed_unit_ids=allowed_ids,
        )

        # Partial matches require confirmation.
        return unit, True

    # ------------------------------------------------------------
    # Fallbacks for replies the rules above did not recognise.
    # ------------------------------------------------------------

    texts = []

    # The whole reply, when it only contains identifier characters.
    if re.fullmatch(
        r"[a-z0-9][a-z0-9 _-]*",
        value.casefold(),
    ):
        texts.append(value)

    # The unit reference inside a short sentence ("the 188 one").
    reference = single_unit_reference(message)

    if reference and reference not in {
        text.casefold() for text in texts
    }:
        texts.append(reference)

    for text in texts:
        compact_unit = find_compact_unit_match(text, units)

        if compact_unit:
            return find_unit(
                compact_unit.unit_id,
                snapshot,
                allowed_unit_ids=allowed_ids,
            )

    if reference:
        partial_matched_id = extract_partial_unit_reference(
            reference,
            units,
        )

        if partial_matched_id:
            unit, _ = find_unit(
                partial_matched_id,
                snapshot,
                allowed_unit_ids=allowed_ids,
            )
            return unit, True

    for text in texts:
        suggestion = typo_suggestion_result(
            text, units, allowed_ids, snapshot,
        )

        if suggestion:
            return suggestion

    # A bare number is a position in the displayed list ("2").
    # Unit-number matches (e.g. "18" -> GRZ-V-18) were tried above
    # and take priority.
    if re.fullmatch(r"\d{1,2}", value) and displayed_ids:
        position = int(value) - 1

        if 0 <= position < len(displayed_ids):
            return find_unit(
                displayed_ids[position],
                snapshot,
                allowed_unit_ids=allowed_ids,
            )

    return None
