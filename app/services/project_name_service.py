import re
import unicodedata


def normalize_project_name(value: str | None) -> str:
    if not value:
        return ""

    text = unicodedata.normalize("NFKC", value).casefold().strip()

    text = re.sub(r"\s+by\s+danube\s*$", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return " ".join(text.split())


SALES_OFFER_PROJECT_ALIASES = {
    "breez": "breez",
    "jewelz": "jewelz residence",
    "wavez": "wavez residence",
    "olivz": "olivz residence",
    "elz": "elz residence",
    "lawnz": "lawnz residence",
    "miraclz": "miraclz tower",
    "glamz": "glamz residence",
    "starz": "starz tower",
    "glitz 1": "glitz residence 1",
    "glitz 2": "glitz residence 2",
    "glitz 3": "glitz residence 3",
    "bayz101": "bayz 101",
    "bayz102": "bayz 102",
    "fashionz": "fashionz 1",
    "viewz": "viewz 1",
}


def normalize_sales_offer_project(value: str | None) -> str:
    normalized = normalize_project_name(value)

    # Normalize spacing in numbered project names.
    normalized = re.sub(
        r"(?<=[a-z])(?=\d)",
        " ",
        normalized,
    )

    # Resolve known marketing-to-inventory aliases.
    return SALES_OFFER_PROJECT_ALIASES.get(
        normalized,
        normalized,
    )
