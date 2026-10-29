
import re


class SalesOfferPlanSelectionError(ValueError):
    pass


ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
}

SMALL_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _unique_ids(ids):
    if not ids:
        raise SalesOfferPlanSelectionError(
            "Please select at least one payment plan."
        )

    if len(ids) != len(set(ids)):
        raise SalesOfferPlanSelectionError(
            "The same payment plan was selected more than once."
        )

    return ids


def select_from_names(selected_names, plans):
    """
    Used when frontend sends:
    selected_payment_plan_names=[...]
    """

    if (
        not isinstance(selected_names, list)
        or not selected_names
        or not all(
            isinstance(name, str) and name.strip()
            for name in selected_names
        )
    ):
        raise SalesOfferPlanSelectionError(
            "Please select at least one valid payment plan."
        )

    mapping = {}

    for plan in plans:
        key = plan["name"].strip().casefold()

        if key in mapping:
            raise SalesOfferPlanSelectionError(
                "Payment-plan names are not unique."
            )

        mapping[key] = plan["id"]

    ids = []

    for name in selected_names:
        key = name.strip().casefold()

        if key not in mapping:
            raise SalesOfferPlanSelectionError(
                "A selected payment plan is no longer "
                "available in the displayed list."
            )

        ids.append(mapping[key])

    return _unique_ids(ids)


def _by_indexes(indexes, plans):
    ids = []

    for number in indexes:
        if number < 1 or number > len(plans):
            raise SalesOfferPlanSelectionError(
                f"Payment plan {number} is not available."
            )

        ids.append(plans[number - 1]["id"])

    return _unique_ids(ids)


def _from_percentages(message, plans):
    """
    Extract explicit percentages from the user's message.

    Examples:
      1% and 0.5%
      0.5%
      10% upfront

    A percentage is accepted only if it identifies
    exactly one plan.
    """

    requested = re.findall(
        r"(?<![\d.])(\d+(?:\.\d+)?)\s*%",
        message,
    )

    if not requested:
        return None

    from decimal import Decimal

    ids = []

    for requested_value in requested:
        target = Decimal(requested_value)

        matches = []

        for plan in plans:
            name_percentages = re.findall(
                r"(?<![\d.])(\d+(?:\.\d+)?)\s*%",
                plan["name"],
            )

            values = {
                Decimal(value)
                for value in name_percentages
            }

            if target in values:
                matches.append(plan)

        if not matches:
            raise SalesOfferPlanSelectionError(
                f"No payment plan matches {requested_value}%."
            )

        if len(matches) > 1:
            raise SalesOfferPlanSelectionError(
                f"Multiple payment plans contain "
                f"{requested_value}%. Please specify "
                "the full plan name or displayed number."
            )

        ids.append(matches[0]["id"])

    return _unique_ids(ids)


def select_from_text(message, plans):
    """
    Resolve typed payment-plan selections against
    the API plans previously saved in Redis.
    """

    text = str(message or "").strip()
    lowered = text.casefold()

    if not text:
        raise SalesOfferPlanSelectionError(
            "Please specify the payment plans."
        )

    # 1. Exact payment-plan name.
    exact = [
        plan["id"]
        for plan in plans
        if plan["name"].strip().casefold() == lowered
    ]

    if exact:
        return _unique_ids(exact)

    # 2. Percentages in plan names.
    percentage_ids = _from_percentages(
        lowered,
        plans,
    )

    if percentage_ids is not None:
        return percentage_ids

    # 3. "first two", "first three", "first 2".
    first_n = re.fullmatch(
        r"(?:select\s+|choose\s+|pick\s+)?"
        r"(?:the\s+)?first\s+"
        r"(\d+|one|two|three|four|five|six|"
        r"seven|eight|nine|ten)"
        r"(?:\s+plans?)?",
        lowered,
    )

    if first_n:
        value = first_n.group(1)

        count = (
            int(value)
            if value.isdigit()
            else SMALL_NUMBERS[value]
        )

        return _by_indexes(
            list(range(1, count + 1)),
            plans,
        )

    # 4. Remove common words and separators.
    normalized = re.sub(
        r"\b(?:select|choose|pick|option|options|"
        r"plan|plans|number|numbers|the|please|"
        r"and|also|payment)\b",
        " ",
        lowered,
    )

    normalized = re.sub(
        r"[,;&+]+",
        " ",
        normalized,
    )

    tokens = normalized.split()

    if not tokens:
        raise SalesOfferPlanSelectionError(
            "Please specify the plan names or numbers."
        )

    indexes = []

    for token in tokens:
        if token in ORDINALS:
            number = ORDINALS[token]

        elif re.fullmatch(r"\d+(?:st|nd|rd|th)?", token):
            number = int(
                re.match(r"\d+", token).group()
            )

        elif re.fullmatch(r"[a-z]", token):
            # A=1, B=2, C=3 ...
            number = ord(token) - ord("a") + 1

        else:
            raise SalesOfferPlanSelectionError(
                "I couldn't identify the payment plans. "
                "Please use their displayed numbers, "
                "letters, percentages, or exact names."
            )

        indexes.append(number)

    return _by_indexes(indexes, plans)
