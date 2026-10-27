
import re
from dataclasses import dataclass

from app.schemas.retrieval import InventorySnapshot


PROJECT_NAME_REQUIRED = (
    "Could you please tell me the project name "
    "so I can share the bank details?"
)


class BankDetailsProjectResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedBankDetailsProject:
    project_id: str
    project_name: str


def _normalize_words(value: str | None) -> str:
    """
    Normalize spacing, case and punctuation,
    while preserving word boundaries.
    """
    text = str(value or "").casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _project_aliases(project_name: str) -> set[str]:
    """
    Supported aliases:
      GREENZ BY DANUBE -> greenz by danube, greenz
      BAYZ 102 BY DANUBE -> bayz 102 by danube, bayz 102

    Do not create aliases from project IDs or unit IDs.
    """
    full_name = _normalize_words(project_name)

    if not full_name:
        return set()

    aliases = {full_name}

    if full_name.endswith(" by danube"):
        short_name = full_name.removesuffix(" by danube").strip()
        if short_name:
            aliases.add(short_name)

    return aliases


def _contains_name(message: str, alias: str) -> bool:
    """
    Match a complete project name or alias as words.

    'bayz 102' matches 'bank details for Bayz 102'
    but not 'bank details for Bayz 1023'.
    """
    if not alias:
        return False

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(alias)
        + r"(?![a-z0-9])"
    )

    return re.search(pattern, message) is not None


def resolve_bank_details_project(
    *,
    message: str,
    snapshot: InventorySnapshot,
    confirmed_project_name: str | None = None,
) -> ResolvedBankDetailsProject:
    """
    Bank Details ONLY.

    Rules:
    - Resolve using a project name explicitly present
      in the current user message.
    - Alternatively, use a trusted, previously confirmed
      project name from this conversation.
    - Never resolve using unit ID, project ID, project
      number, unit name or bank account number.
    - Never trust an LLM-inferred project_name alone.
    """

    normalized_message = _normalize_words(message)

    if not normalized_message and not confirmed_project_name:
        raise BankDetailsProjectResolutionError(
            PROJECT_NAME_REQUIRED
        )

    projects = []

    for project in snapshot.projects:
        if not project.project_id or not project.project_name:
            continue

        projects.append(
            ResolvedBankDetailsProject(
                project_id=str(project.project_id),
                project_name=project.project_name,
            )
        )

    matches = []

    for project in projects:
        matched_aliases = [
            alias
            for alias in _project_aliases(project.project_name)
            if _contains_name(normalized_message, alias)
        ]

        if matched_aliases:
            longest_alias = max(
                matched_aliases,
                key=lambda value: len(value.split()),
            )

            matches.append(
                (len(longest_alias.split()), project)
            )

    if matches:
        highest_score = max(score for score, _ in matches)

        best_matches = [
            project
            for score, project in matches
            if score == highest_score
        ]

        # Remove duplicate project IDs.
        unique = {
            project.project_id: project
            for project in best_matches
        }

        if len(unique) == 1:
            return next(iter(unique.values()))

        raise BankDetailsProjectResolutionError(
            "Multiple projects match your request. "
            "Could you please confirm the project name?"
        )

    if confirmed_project_name:
        normalized_confirmed = _normalize_words(
            confirmed_project_name
        )

        confirmed_matches = [
            project
            for project in projects
            if normalized_confirmed
            in _project_aliases(project.project_name)
        ]

        if len(confirmed_matches) == 1:
            return confirmed_matches[0]

    # 3. No valid project name: stop before the API call.
    raise BankDetailsProjectResolutionError(
        PROJECT_NAME_REQUIRED
    )
