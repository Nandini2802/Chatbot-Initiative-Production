import re

FLOOR_PATTERN = re.compile(
    r"(?:^|-)F(\d+)(?=-|$)",
    re.IGNORECASE,
)

GROUND_FLOOR_PATTERN = re.compile(
    r"(?:^|-)GF(?=-|$)",
    re.IGNORECASE,
)


def extract_floor_from_name(
    unit_name: str | None,
) -> int | None:
    """
    Examples:
        SRNZ-A-F01-101      -> 1
        B101Z-F100-10007    -> 100
        ETZ-3-A-F37-3705    -> 37
        OAZ-1-GF-RETAIL 02  -> 0

    Returns None if the name has no recognized floor.
    """

    if not unit_name:
        return None

    name = str(unit_name).strip()

    match = FLOOR_PATTERN.search(name)

    if match:
        return int(match.group(1))

    if GROUND_FLOOR_PATTERN.search(name):
        return 0

    return None


def parse_floor_value(value) -> int | None:
    """
    Normalizes floor values from Salesforce or router.

    Supported:
        20, "20", "020", "F20", "GF",
        "Ground Floor", "20th floor"
    """

    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value if value >= 0 else None

    text = str(value).strip().upper()

    if text in {
        "GF",
        "G",
        "GROUND",
        "GROUND FLOOR",
    }:
        return 0

    match = re.fullmatch(
        r"F?0*(\d+)(?:ST|ND|RD|TH)?"
        r"(?:\s*FLOOR)?",
        text,
    )

    if match:
        return int(match.group(1))

    return None


def get_unit_floor(unit) -> int | None:
    """
    Prefer the floor encoded in the unit name.

    Fallback order:
        1. unit_name
        2. floor_number (Salesforce)
        3. floor_code (Salesforce)

    If the name contains a recognized floor, that
    value is authoritative for this feature.
    """

    floor = extract_floor_from_name(
        getattr(unit, "unit_name", None)
    )

    if floor is not None:
        return floor

    for value in (
        getattr(unit, "floor_number", None),
        getattr(unit, "floor_code", None),
    ):
        floor = parse_floor_value(value)

        if floor is not None:
            return floor

    return None


def matches_floor_filter(
    floor: int | None,
    exact_floor: str | None = None,
    min_floor: int | None = None,
    max_floor: int | None = None,
    min_inclusive: bool = True,
    max_inclusive: bool = True,
) -> bool:
    """
    Applies exact floor and range conditions.
    Unknown floors never match an active filter.
    """

    has_filter = any(
        value is not None
        for value in (
            exact_floor,
            min_floor,
            max_floor,
        )
    )

    if not has_filter:
        return True

    if floor is None:
        return False

    if exact_floor is not None:
        requested = parse_floor_value(exact_floor)

        if requested is None or floor != requested:
            return False

    if min_floor is not None:
        if min_inclusive:
            if floor < min_floor:
                return False
        else:
            if floor <= min_floor:
                return False

    if max_floor is not None:
        if max_inclusive:
            if floor > max_floor:
                return False
        else:
            if floor >= max_floor:
                return False

    return True
