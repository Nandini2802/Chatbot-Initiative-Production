
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata


@dataclass(frozen=True)
class Resolution:
    status: str  # matched | ambiguous | not_found
    name: str | None = None
    candidates: tuple[str, ...] = ()
    method: str = ""


def norm(value: str | None) -> str:
    text = unicodedata.normalize(
        "NFKC", str(value or "")
    ).casefold()

    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+by\s+danube$", "", text)

    return " ".join(text.split())



def similarity(left: str, right: str) -> float:
    def canonical(text):
        return " ".join(
            word[:-1] + "z"
            if len(word) > 3 and word.endswith("s")
            else word
            for word in text.split()
        )

    return max(
        SequenceMatcher(None, left, right).ratio(),
        SequenceMatcher(
            None,
            canonical(left),
            canonical(right),
        ).ratio(),
    )


# Keep explicitly approved project families.
MARKETING_FAMILIES = {
    "eleganz": {"1", "2", "3", "4", "5", "6"},
}


def is_approved_marketing_family(
    reference: str | None,
    catalog_project: str | None,
) -> bool:
    """
    Check whether a numbered project reference
    is approved to use the parent project's
    marketing collateral.

    Example:
        ELEGANZ 3 -> ELEGANZ

    Only explicitly approved family mappings
    are accepted.
    """

    query = normalize_marketing_project(reference)
    target = normalize_marketing_project(
        catalog_project
    )

    match = re.fullmatch(
        r"(.+?)\s+(\d+)",
        query,
    )

    if not match:
        return False

    family, number = match.groups()

    return (
        target == family
        and number in MARKETING_FAMILIES.get(
            family, set()
        )
    )



# Your final approved marketing asset aliases.
ASSET_ALIASES = {
    "floor plan": [
        "floor plan", "floor plans",
        "floorplan", "floorplans",
        "flor plan", "flor plans",
    ],
    "brochure": [
        "brochure", "brochures",
        "brochre", "brochr", "brocher",
    ],
    "video": [
        "video", "videos",
        "vidio", "vidios", "vedio",
    ],
    "amenities": [
        "amenities", "amenity",
        "amenties", "amnties",
    ],
    "exterior": [
        "exterior", "exteriors",
        "exterir", "external images",
    ],
    "interiors": [
        "interior", "interiors",
        "interir", "internal images",
    ],
    "ppt": [
        "ppt", "pptx",
        "presentation", "powerpoint",
        "power point",
    ],
    "renders": [
        "render", "renders",
        "rendering", "renderings",
        "rendar", "rander",
    ],
    "price list": [
        "price list", "price lists",
        "pricelist", "price sheet",
        "price lis", "pric list",
    ],
    "all": [
        "all marketing materials",
        "all collateral", "all materials",
    ],
    "social-media": [
        "social media", "social media assets",
    ],
    "factsheet": [
        "factsheet", "fact sheet",
    ],
    "other": [
        "other materials",
    ],
    "walkthrough": [
        "walkthrough", "walk through",
        "walkthrough video",
    ],
}


def normalize_marketing_project(
    value: str | None,
) -> str:
    text = norm(value)

    # Normalize BAYZ101 and GLITZ3.
    text = re.sub(
        r"(?<=[a-z])(?=\d)", " ", text
    )
    text = re.sub(
        r"(?<=\d)(?=[a-z])", " ", text
    )

    # Remove generic project-description words.
    text = re.sub(
        r"\btower\b",
        " ",
        text,
    )

    return " ".join(text.split())


def project_numbers(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\b\d+\b", value))


def resolve_marketing_project(
    reference: str | None,
    marketing_projects: list[str],
) -> Resolution:
    query = normalize_marketing_project(reference)

    catalog = sorted({
        name.strip()
        for name in marketing_projects
        if isinstance(name, str) and name.strip()
    })

    if not query or not catalog:
        return Resolution("not_found")

    normalized = [
        (name, normalize_marketing_project(name))
        for name in catalog
    ]

    # 1. Exact normalized match.
    exact = [
        name for name, key in normalized
        if key == query
    ]

    if len(exact) == 1:
        return Resolution(
            "matched", exact[0], method="exact"
        )

    if len(exact) > 1:
        return Resolution(
            "ambiguous",
            candidates=tuple(exact),
        )

    # 2. Explicitly approved numbered families.
    family_match = re.fullmatch(
        r"(.+?)\s+(\d+)", query
    )

    if family_match:
        family, number = family_match.groups()

        for base, allowed in MARKETING_FAMILIES.items():
            if number not in allowed:
                continue

            if (
                family == base
                or similarity(family, base) >= 0.82
            ):
                destinations = [
                    name for name, key in normalized
                    if key == base
                ]

                if len(destinations) == 1:
                    return Resolution(
                        "matched",
                        destinations[0],
                        method="family_alias",
                    )

    # 3. Fuzzy match only projects with
    # identical number sequences.
    query_nums = project_numbers(query)

    ranked = []

    for name, key in normalized:
        if project_numbers(key) != query_nums:
            continue

        score = similarity(query, key)
        ranked.append((score, name))

    ranked.sort(
        key=lambda item: (-item[0], item[1])
    )

    if not ranked:
        return Resolution("not_found")

    best_score, best_name = ranked[0]

    if best_score < 0.78:
        return Resolution("not_found")

    # Protect against near-equal project candidates.
    if (
        len(ranked) > 1
        and best_score - ranked[1][0] < 0.09
    ):
        return Resolution(
            "ambiguous",
            candidates=tuple(
                name for _, name in ranked[:3]
            ),
        )

    return Resolution(
        "matched",
        best_name,
        method="fuzzy",
    )


def resolve_marketing_asset(
    value: str | None,
) -> Resolution:
    query = norm(value)

    if not query:
        return Resolution("not_found")

    best_by_type = {}

    for canonical, aliases in ASSET_ALIASES.items():
        for alias in [canonical, *aliases]:
            key = norm(alias)

            if query == key:
                return Resolution(
                    "matched",
                    canonical,
                    method="alias",
                )

            score = similarity(query, key)

            best_by_type[canonical] = max(
                score,
                best_by_type.get(canonical, 0.0),
            )

    ranked = sorted(
        (
            (score, name)
            for name, score in best_by_type.items()
        ),
        key=lambda item: (-item[0], item[1]),
    )

    if not ranked or ranked[0][0] < 0.78:
        return Resolution("not_found")

    if (
        len(ranked) > 1
        and ranked[0][0] - ranked[1][0] < 0.09
    ):
        return Resolution(
            "ambiguous",
            candidates=tuple(
                name for _, name in ranked[:3]
            ),
        )

    return Resolution(
        "matched",
        ranked[0][1],
        method="fuzzy",
    )


def resolve_assets(
    values: list[str] | None,
) -> tuple[list[str], list[str]]:
    resolved = []
    unresolved = []

    for value in values or []:
        match = resolve_marketing_asset(value)

        if match.status == "matched":
            if match.name not in resolved:
                resolved.append(match.name)
        else:
            unresolved.append(value)

    return resolved, unresolved



REQUEST_PREFIX = re.compile(
    r"^(?:(?:please|can you|could you|"
    r"show me|show|give me|give|"
    r"download|send me|send|"
    r"get me|get|fetch|provide|"
    r"i want|i need|"
    r"marketing materials?|"
    r"materials?|collateral|"
    r"for|of)\s+)+",
    re.IGNORECASE,
)


def clean_project_phrase(value: str) -> str:
    """
    Remove generic request words from the beginning.

    Preserve:
    - project numbers
    - residence / residences
    - tower
    """

    text = norm(value)

    previous = None

    while text != previous:
        previous = text

        text = REQUEST_PREFIX.sub(
            "",
            text,
        ).strip()

    return text


def extract_marketing_parts(
    message: str,
) -> tuple[str | None, list[str]]:
    """
    Extract the project reference and requested
    marketing material from the original message.

    The extracted project is not necessarily a
    canonical catalog name. Project resolution
    happens separately.

    Returns:
        (project_reference, marketing_assets)
    """

    text = norm(message)

    if not text:
        return None, []


    asset_first = re.fullmatch(
        r"(.+?)\s+(?:of|for)\s+(.+)",
        text,
    )

    if asset_first:

        left, right = asset_first.groups()

        asset_phrase = clean_project_phrase(left)

        asset_match = resolve_marketing_asset(
            asset_phrase
        )

        if asset_match.status == "matched":

            project_phrase = clean_project_phrase(
                right
            )

            if project_phrase:
                return (
                    project_phrase,
                    [asset_match.name],
                )

    words = text.split()

    # An asset can contain multiple words:
    # floor plan, price list, social media, etc.
    #
    # Preserve at least one word for the project.
    max_words = min(
        4,
        len(words) - 1,
    )

    # First try exact asset aliases.
    # This avoids unnecessary fuzzy matching.
    for size in range(max_words, 0, -1):

        asset_words = words[-size:]

        # Never consume a standalone project number
        # as part of an asset phrase.
        if any(
            word.isdigit()
            for word in asset_words
        ):
            continue

        asset_phrase = " ".join(asset_words)

        exact_asset = None

        for canonical, aliases in ASSET_ALIASES.items():

            valid_names = [
                canonical,
                *aliases,
            ]

            if any(
                norm(alias) == asset_phrase
                for alias in valid_names
            ):
                exact_asset = canonical
                break

        if exact_asset:

            remaining = " ".join(
                words[:-size]
            )

            project_phrase = clean_project_phrase(
                remaining
            )

            if project_phrase:
                return (
                    project_phrase,
                    [exact_asset],
                )

    fuzzy_max_words = min(
        3,
        len(words) - 1,
    )

    for size in range(fuzzy_max_words, 0, -1):

        asset_words = words[-size:]

        if any(
            word.isdigit()
            for word in asset_words
        ):
            continue

        asset_phrase = " ".join(
            asset_words
        )

        asset_match = resolve_marketing_asset(
            asset_phrase
        )

        if asset_match.status != "matched":
            continue

        remaining = " ".join(
            words[:-size]
        )

        project_phrase = clean_project_phrase(
            remaining
        )

        if project_phrase:
            return (
                project_phrase,
                [asset_match.name],
            )

    project_phrase = clean_project_phrase(
        text
    )

    return (
        project_phrase or None,
        [],
    )



@dataclass(frozen=True)
class MarketingQueryResolution:
    project: Resolution
    assets: tuple[str, ...]
    unresolved_assets: tuple[str, ...]


def resolve_marketing_query(
    message: str,
    marketing_projects: list[str],
    router_project: str | None = None,
    router_assets: list[str] | None = None,
) -> MarketingQueryResolution:
    """
    Resolve a marketing query against the live
    marketing catalog.

    Prefer the Router's extracted fields when
    they resolve. Fall back to the original
    message for incomplete extraction.
    """

    extracted_project, extracted_assets = (
        extract_marketing_parts(message)
    )

    project = resolve_marketing_project(
        router_project,
        marketing_projects,
    )

    # Fall back only when Router project
    # could not be resolved.
    if project.status == "not_found":
        project = resolve_marketing_project(
            extracted_project,
            marketing_projects,
        )

    assets, unresolved = resolve_assets(
        router_assets
    )

    # Recover assets when Router missed them.
    if not assets and not router_assets:
        assets = extracted_assets

    return MarketingQueryResolution(
        project=project,
        assets=tuple(assets),
        unresolved_assets=tuple(unresolved),
    )
