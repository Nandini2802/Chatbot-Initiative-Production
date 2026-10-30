import re
import unicodedata
from rapidfuzz import fuzz


def normalize_text(value) -> str:
    text = unicodedata.normalize(
        "NFKC", str(value or "")
    ).casefold()

    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def tokens(value) -> set[str]:
    return set(normalize_text(value).split())


class InventoryAttributeResolver:

    # Only explicitly approved equivalent terminology.
    ALIASES = {
        "sports city": "dubai sports city",
        "1 bhk": "1 bedroom",
        "1 bed": "1 bedroom",
        "2 bhk": "2 bedroom",
        "2 bed": "2 bedroom",
        "3 bhk": "3 bedroom",
        "3 bed": "3 bedroom",
        "4 bhk": "4 bedroom",
        "4 bed": "4 bedroom",
        "offplan": "off plan",
    }

    @classmethod
    def canonical(cls, value: str) -> str:
        value = normalize_text(value)
        return cls.ALIASES.get(value, value)

    @classmethod
    def match(
        cls,
        requested: str | None,
        actual: str | None,
        *,
        allow_components: bool = False,
    ) -> bool:

        if not requested or not actual:
            return False

        requested_norm = cls.canonical(requested)
        actual_norm = cls.canonical(actual)

        if requested_norm == actual_norm:
            return True

        requested_tokens = tokens(requested_norm)
        actual_tokens = tokens(actual_norm)

        if not requested_tokens or not actual_tokens:
            return False

        # Recognize explicit compound descriptions.
        # "city view" matches "canal view & city view".
        if allow_components:
            if requested_tokens.issubset(actual_tokens):
                return True

        # Partial named types:
        # "presidential" -> "Presidential Suite"
        if not allow_components:
            if (
                len(requested_norm) >= 5
                and requested_tokens.issubset(actual_tokens)
            ):
                return True

        # Fuzzy matching is intentionally conservative.
        # Do not fuzzy-match a short word such as "sea"
        # against unrelated view names.
        if len(requested_norm) < 6:
            return False

        score = fuzz.ratio(
            requested_norm,
            actual_norm,
        )

        return score >= 90

    @classmethod
    def match_view(
        cls,
        requested: str | None,
        actual: str | None,
    ) -> bool:

        if not requested or not actual:
            return False

        requested_norm = normalize_text(requested)
        actual_norm = normalize_text(actual)

        # A request for multiple view components must
        # satisfy every component.
        parts = [
            p.strip()
            for p in re.split(
                r"\s+(?:and)\s+|\s*&\s*|,",
                requested_norm.replace(" & ", " and "),
            )
            if p.strip()
        ]

        if len(parts) > 1:
            return all(
                cls.match(
                    part,
                    actual_norm,
                    allow_components=True,
                )
                for part in parts
            )

        return cls.match(
            requested_norm,
            actual_norm,
            allow_components=True,
        )