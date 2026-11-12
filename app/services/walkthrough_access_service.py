
"""Excel walkthrough engine using request feature keys."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from app.services.feature_access_service import (
    parse_key_features,
)


ROOT = Path(__file__).resolve().parent

WALKTHROUGH_FILE = "Danube One App Walkthrough(1).xlsx"


# Walkthroughs where ANY ONE of the keys in the workbook's Feature Key cell
# is enough (elsewhere "A/B" or "A,B" means all are needed). The keys
# themselves always come from the workbook, e.g. "DARView,DARCreate".
ANY_KEY_FEATURES: frozenset[str] = frozenset({
    "daily activity report",
})


def norm(value) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").replace("\xa0", " "),
    ).strip().casefold()


def compact_feature_key(value) -> str:
    """'DAR Dashboard', 'DARdashboard', 'DAR_Dashboard' -> 'dardashboard'."""
    return re.sub(
        r"[\s_\-]+",
        "",
        str(value or "").replace("\xa0", " "),
    ).casefold()


def granted_feature_keys(key_features: str | None) -> set[str]:
    """The app's comma-separated feature keys, compacted."""
    return {
        compact
        for compact in (
            compact_feature_key(key)
            for key in parse_key_features(key_features)
        )
        if compact
    }


def rows_xlsx(path: Path):
    book = load_workbook(
        path,
        read_only=True,
        data_only=True,
    )
    try:
        return [list(row) for row in book.active.values]
    finally:
        book.close()


def cell(row, col):
    return row[col] if col < len(row) else None


@dataclass(frozen=True)
class Guide:
    name: str
    steps: str
    key: str


class WalkthroughEngine:

    def __init__(self, directory=ROOT):
        directory = Path(directory)

        self.guides: dict[str, Guide] = {}

        excel_path = directory / WALKTHROUGH_FILE

        rows = rows_xlsx(excel_path)

        # Two layouts are supported:
        #   - all steps in one cell (line breaks between steps), or
        #   - one step per row, with the S. No., Feature Name and Feature
        #     Key only on the first row (merged cells). A row with no
        #     S. No. and no Feature Name continues the walkthrough above.
        entries: dict[str, dict] = {}
        current: dict | None = None

        # Row 1 = Excel header
        for row in rows[1:]:

            serial = str(cell(row, 0) or "").strip()
            feature_name = norm(cell(row, 1))
            steps = str(cell(row, 2) or "").strip()
            feature_key = str(cell(row, 3) or "").strip()

            if not feature_name:
                if not serial and current is not None:
                    if steps:
                        current["steps"].append(steps)
                    if feature_key and not current["key"]:
                        current["key"] = feature_key
                else:
                    # A new numbered row without a name ends the walkthrough.
                    current = None
                continue

            if feature_name.startswith("based on the login"):
                current = None
                continue

            if feature_name in entries:
                raise ValueError(
                    f"Duplicate walkthrough feature: {feature_name}"
                )

            current = {
                "name": str(cell(row, 1)).strip(),
                "steps": [steps] if steps else [],
                "key": feature_key,
            }
            entries[feature_name] = current

        for feature_name, entry in entries.items():
            if not entry["steps"]:
                continue

            self.guides[feature_name] = Guide(
                name=entry["name"],
                steps="\n".join(entry["steps"]),
                key=entry["key"],
            )

        self.issues = self.validate()

    def validate(self):
        issues = []

        for guide in self.guides.values():
            if not guide.key:
                issues.append(
                    f"Missing Feature Key: {guide.name}"
                )

        return issues

    def required_keys(self, name: str) -> list[str]:
        """The guide's feature key(s), compacted. Empty if unknown.

        For ANY_KEY_FEATURES these are the alternatives (any one is enough).
        """

        guide = self.guides.get(norm(name))

        if guide is None or not guide.key:
            return []

        return [
            compact
            for compact in (
                compact_feature_key(key)
                for key in re.split(r"[/,|]", guide.key)
            )
            if compact
        ]

    def permission(
        self,
        name: str,
        key_features: str | None,
    ) -> tuple[bool, str]:

        feature_name = norm(name)

        guide = self.guides.get(feature_name)

        if guide is None:
            return False, "unknown_feature"

        if not guide.key:
            return False, "missing_excel_feature_key"

        if feature_name in ANY_KEY_FEATURES:
            granted = granted_feature_keys(key_features)

            if any(
                compact in granted
                for compact in self.required_keys(name)
            ):
                return True, "feature_key_verified"

            return False, "feature_key_not_granted"

        # Keys are compared ignoring case, spaces, dashes and
        # underscores, so the workbook's "DAR Dashboard" matches the
        # app's "DARdashboard" / "DAR_Dashboard". Different key names
        # (e.g. "DarAnalytics") still never match.
        required_keys = self.required_keys(name)

        granted_keys = granted_feature_keys(key_features)

        if (
            not required_keys
            or not all(
                key in granted_keys
                for key in required_keys
            )
        ):
            return False, "feature_key_not_granted"

        return True, "feature_key_verified"

    def lookup(
        self,
        feature: str,
        key_features: str | None,
    ) -> dict:

        allowed, reason = self.permission(
            name=feature,
            key_features=key_features,
        )

        if not allowed:
            return {
                "status": "denied",
                "reason": reason,
            }

        guide = self.guides[norm(feature)]

        return {
            "status": "ok",
            "feature": guide.name,
            "steps": guide.steps,
        }
