
import re

from app.services.sales_offer_resolver import (
    find_unit,
    SalesOfferResolutionError,
)


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

    # Existing resolver supports normalized identifiers.
    # Only attempt this for a standalone unit reference.
    value = message.strip()

    if re.fullmatch(
        r"[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)+",
        value,
    ):
        return find_unit(
            value,
            snapshot,
            allowed_unit_ids=allowed_ids,
        )

    return None
