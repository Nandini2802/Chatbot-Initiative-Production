
import re

from app.services.project_name_service import (
    normalize_project_name,
)


class SalesOfferResolutionError(Exception):
    pass


def normalize_unit_identifier(value: str | None) -> str:
    """
    GRZ-TH-808 -> grzth808
    grzth808   -> grzth808
    """
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").casefold(),
    )


def find_project_units(intent, snapshot):
    """
    Resolve a project name, Salesforce project ID,
    or project number against authorized inventory.
    """

    requested_ids = set()
    requested_names = set()

    if getattr(intent, "project_id", None):
        requested_ids.add(
            str(intent.project_id).strip().casefold()
        )

    if getattr(intent, "project_name", None):
        requested_names.add(
            normalize_project_name(intent.project_name)
        )

    if getattr(intent, "project_number", None):
        requested_number = str(
            intent.project_number
        ).strip().casefold()

        for project in snapshot.projects:
            if (
                project.project_id
                and str(
                    project.project_number or ""
                ).strip().casefold() == requested_number
            ):
                requested_ids.add(
                    project.project_id.casefold()
                )

    # Resolve project names to their IDs.
    for project in snapshot.projects:
        if (
            project.project_id
            and normalize_project_name(
                project.project_name or ""
            ) in requested_names
        ):
            requested_ids.add(
                project.project_id.casefold()
            )

    return [
        unit
        for unit in snapshot.units
        if unit.unit_id
        and (
            (
                unit.project_id
                and unit.project_id.casefold()
                in requested_ids
            )
            or (
                unit.project_name
                and normalize_project_name(
                    unit.project_name
                ) in requested_names
            )
        )
    ]


PROJECT_UNIT_PREFIXES = {
    "aspirz": ("aspz",),
    "shahrukhz": ("srkz",),
    "eleganz": ("elgz",),
    "greenz": ("grz",),
    "diamondz": ("dmz",),
    "elitz": ("etz",),
    "fashionz": ("fnz",),
    "oasiz": ("oaz",),
    "oceanz": ("ocz",),
    "viewz": ("vwz",),
    "jewelz": ("jwz",),
    "resortz": ("rszb2",),
    "bayz 102": ("b102z",),
    "timez": ("tmz",),
    "sparklz": ("splz",),
}


def _unit_segments(value):
    """
    ASPZ-F02-11013 -> ['aspz', 'f02', '11013']
    ETZ-2-B-GR-Shop-7 ->
        ['etz', '2', 'b', 'gr', 'shop', '7']
    """
    return re.findall(
        r"[a-z0-9]+",
        str(value or "").casefold(),
    )


def _unit_forms(unit):
    """
    Extract searchable unit-name and unit-code
    segments.
    """
    return [
        _unit_segments(value)
        for value in (
            getattr(unit, "unit_name", None),
            getattr(unit, "unit_code", None),
        )
        if value
    ]


def _suffix_matches(query, parts):
    """
    Match complete trailing segments.

    Examples:
        F09-907 -> ETZ-2-A-F09-907
        f09907  -> ETZ-2-A-F09-907
        907     -> ETZ-2-A-F09-907
        grshop7 -> ETZ-2-B-GR-Shop-7
    """
    if not query or not parts:
        return False

    query_parts = _unit_segments(query)

    if not query_parts:
        return False

    # Match complete trailing segments.
    if (
        len(query_parts) <= len(parts)
        and parts[-len(query_parts):] == query_parts
    ):
        return True

    compressed = normalize_unit_identifier(query)

    # Match compressed trailing segments.
    # Require at least two complete segments.
    return any(
        compressed == "".join(parts[-n:])
        for n in range(2, len(parts) + 1)
    )


def _project_prefixes(name):
    """
    Resolve project hints to inventory prefixes.

    Examples:
        Eleganz -> elgz
        Elitz   -> etz
        Oceanz  -> ocz
        Bayz102 -> b102z
    """
    normalized = normalize_project_name(name)

    normalized = re.sub(
        r"(?<=[a-z])(?=\d)",
        " ",
        normalized,
    )

    return PROJECT_UNIT_PREFIXES.get(
        normalized,
        (),
    )


def _matches_reference(requested, unit):
    """
    Match partial identifiers against a unit.

    Supports:
        Eleganz 001
        Elitz 907
        Oceanz Restaurant 1
        Oceanz Retail 1
        Bayz 102 8209
        Elitz Shop 7
        F09-907
        f09907
        f828209d
        grshop7
        001

    Does not bypass inventory authorization.
    """

    query = str(requested or "").strip()
    qparts = _unit_segments(query)

    if not qparts:
        return False


    for split in range(1, len(qparts)):
        project_hint = " ".join(qparts[:split])

        prefixes = _project_prefixes(
            project_hint
        )

        if not prefixes:
            continue

        tail = " ".join(qparts[split:])

        for parts in _unit_forms(unit):
            if not parts:
                continue

            if parts[0] not in prefixes:
                continue

            if _suffix_matches(tail, parts):
                return True

            # Optional trailing unit variant:
            # 8209 -> 8209-D
            if (
                len(parts) >= 2
                and len(parts[-1]) == 1
                and parts[-1].isalpha()
                and _suffix_matches(
                    tail,
                    parts[:-1],
                )
            ):
                return True

    for parts in _unit_forms(unit):
        if _suffix_matches(query, parts):

            # Reject a single short alphabetic
            # token as a unit reference.
            if (
                len(qparts) == 1
                and qparts[0].isalpha()
            ):
                continue

            return True

        # Match optional trailing letter variants.
        if (
            len(parts) >= 2
            and len(parts[-1]) == 1
            and parts[-1].isalpha()
            and _suffix_matches(
                query,
                parts[:-1],
            )
        ):
            return True

    return False


def find_unit(
    requested,
    snapshot,
    allowed_unit_ids=None,
):
    """
    Resolve a unit against authorized inventory.

    Returns:
        (unit, False)
            Exact full identifier.

        (unit, True)
            Normalized or partial match
            requiring confirmation.

    Never automatically selects an
    ambiguous unit.
    """

    requested = str(
        requested or ""
    ).strip()

    if not requested:
        raise SalesOfferResolutionError(
            "Please specify a unit."
        )

    allowed = (
        set(allowed_unit_ids)
        if allowed_unit_ids is not None
        else None
    )

    units = [
        unit
        for unit in snapshot.units
        if getattr(unit, "unit_id", None)
        and (
            allowed is None
            or unit.unit_id in allowed
        )
    ]

    def choose(matches, confirmation):
        unique = {
            unit.unit_id: unit
            for unit in matches
        }

        if len(unique) == 1:
            return (
                next(iter(unique.values())),
                confirmation,
            )

        if len(unique) > 1:
            raise SalesOfferResolutionError(
                "Multiple authorized units match "
                "that reference. Please provide "
                "the full unit name, including "
                "tower or floor."
            )

        return None

    direct = choose(
        [
            unit
            for unit in units
            if any(
                str(value).strip().casefold()
                == requested.casefold()
                for value in (
                    unit.unit_id,
                    unit.unit_name,
                    unit.unit_code,
                )
                if value
            )
        ],
        False,
    )

    if direct:
        return direct

    normalized = normalize_unit_identifier(
        requested
    )

    full = choose(
        [
            unit
            for unit in units
            if any(
                normalize_unit_identifier(value)
                == normalized
                for value in (
                    unit.unit_id,
                    unit.unit_name,
                    unit.unit_code,
                )
                if value
            )
        ],
        True,
    )

    if full:
        return full


    partial = choose(
        [
            unit
            for unit in units
            if _matches_reference(
                requested,
                unit,
            )
        ],
        True,
    )

    if partial:
        return partial

    raise SalesOfferResolutionError(
        "I couldn't find that unit in your "
        "authorized inventory."
    )


def extract_explicit_sales_offer_unit_reference(
    message,
    snapshot,
):
    """
    Extract a unit reference from an explicit
    sales-offer request.

    Returns None for project-only requests.

    The returned reference must still be
    validated using find_unit().
    """

    match = re.search(
        r"\b(?:generate\s+)?sales\s+offer\s+"
        r"(?:for|of)\s+(.+?)\s*$",
        str(message or ""),
        re.IGNORECASE,
    )

    if not match:
        return None

    raw = (
        match.group(1)
        .strip()
        .rstrip("?.!,")
    )

    # Project number is not a unit number.
    if re.match(
        r"^project\s+"
        r"(?:number\s+|no\.?\s+|id\s+)?",
        raw,
        re.IGNORECASE,
    ):
        return None

    # Preserve existing project-only requests.
    from app.services.sales_offer_project_resolver import (
        resolve_sales_offer_project,
    )

    project_match = resolve_sales_offer_project(
        raw,
        snapshot,
    )

    if project_match.status in (
        "matched",
        "ambiguous",
    ):
        return None

    # Remove leading unit labels.
    candidate = re.sub(
        r"^unit\s*"
        r"(?:(?:number|no\.?|code|name)\s*)?",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()

    if not candidate:
        return None

    try:
        find_unit(
            candidate,
            snapshot,
        )
        return candidate

    except SalesOfferResolutionError as exc:
        # Ambiguous references must still reach
        # the handler for clarification.
        if (
            "Multiple authorized units"
            in str(exc)
        ):
            return candidate


    parts = _unit_segments(candidate)

    if not parts:
        return None

    if re.search(
        r"\d",
        candidate,
    ) and (
        len(parts) >= 2
        or len(parts[0]) >= 4
    ):
        return candidate

    return None
