
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


def norm(value) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").replace("\xa0", " "),
    ).strip().casefold()


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

        # Row 1 = Excel header
        for row in rows[1:]:

            feature_name = norm(cell(row, 1))
            steps = str(cell(row, 2) or "").strip()
            feature_key = str(cell(row, 3) or "").strip()

            if not feature_name or not steps:
                continue

            if feature_name.startswith("based on the login"):
                continue

            if feature_name in self.guides:
                raise ValueError(
                    f"Duplicate walkthrough feature: {feature_name}"
                )

            self.guides[feature_name] = Guide(
                name=str(cell(row, 1)).strip(),
                steps=steps,
                key=feature_key,
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

        required_keys = [
            key.strip().casefold()
            for key in re.split(r"[/,|]", guide.key)
            if key.strip()
        ]

        granted_keys = parse_key_features(key_features)

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
