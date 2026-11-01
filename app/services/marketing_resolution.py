
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
            None, canonical(left), canonical(right)
        ).ratio(),
    )


MARKETING_FAMILIES = {
    "eleganz": {"1", "2", "3", "4", "5", "6"},
}


def resolve_marketing_project(
    reference: str | None,
    marketing_projects: list[str],
) -> Resolution:
    query = norm(reference)
    catalog = sorted({
        name.strip()
        for name in marketing_projects
        if isinstance(name, str) and name.strip()
    })

    if not query or not catalog:
        return Resolution("not_found")

    normalized = [(name, norm(name)) for name in catalog]

    # 1. Exact canonical marketing name wins.
    exact = [name for name, key in normalized if key == query]
    if len(exact) == 1:
        return Resolution("matched", exact[0], method="exact")
    if len(exact) > 1:
        return Resolution("ambiguous", candidates=tuple(exact))

    # 2. Only explicitly approved numbered-family mappings.
    #
    # ELEGANZ 2 BY DANUBE -> ELEGANZ
    # BAYZ 102 remains BAYZ 102.
    match = re.fullmatch(r"(.+?)\s+(\d+)", query)

    if match:
        family, number = match.groups()

        for base, allowed_numbers in MARKETING_FAMILIES.items():
            if number not in allowed_numbers:
                continue

            if family == base or similarity(family, base) >= 0.82:
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

    # 3. Guarded typo matching.
    #
    # Numbers must match, except for the explicitly
    # approved family aliases handled above.
    query_numbers = tuple(re.findall(r"\b\d+\b", query))

    ranked = []
    for name, key in normalized:
        numbers = tuple(re.findall(r"\b\d+\b", key))
        if query_numbers != numbers:
            continue

        score = similarity(query, key)
        ranked.append((score, name))

    ranked.sort(key=lambda item: (-item[0], item[1]))

    if not ranked or ranked[0][0] < 0.78:
        return Resolution("not_found")

    best_score, best_name = ranked[0]

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
        "all collateral", "all materials"
    ],
        "social-media": [
        "social media", "social media assets"
    ],
    "factsheet": [
        "factsheet", "fact sheet"
    ],
    "other": [
        "other materials"
    ],
    "walkthrough": [
        "walkthrough", "walk through",
        "walkthrough video"
    ],
}


def resolve_marketing_asset(
    value: str | None,
) -> Resolution:
    query = norm(value)

    if not query:
        return Resolution("not_found")

    candidates = []

    for canonical, aliases in ASSET_ALIASES.items():
        for alias in [canonical, *aliases]:
            key = norm(alias)

            if query == key:
                return Resolution(
                    "matched", canonical, method="alias"
                )

            score = similarity(query, key)
            candidates.append((score, canonical))

    best_by_type = {}
    for score, canonical in candidates:
        best_by_type[canonical] = max(
            score, best_by_type.get(canonical, 0.0)
        )

    ranked = sorted(
        ((score, name) for name, score in best_by_type.items()),
        reverse=True,
    )

    if not ranked or ranked[0][0] < 0.78:
        return Resolution("not_found")

    if (
        len(ranked) > 1
        and ranked[0][0] - ranked[1][0] < 0.09
    ):
        return Resolution(
            "ambiguous",
            candidates=tuple(name for _, name in ranked[:3]),
        )

    return Resolution(
        "matched", ranked[0][1], method="fuzzy"
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
