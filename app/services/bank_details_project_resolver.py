"""Bank-only requirement: project name must be stated in the message
or already explicitly confirmed in this session. Never resolve using unit IDs.
"""
from dataclasses import dataclass
from app.services.project_resolution_service import (
    match_project_in_message,
    match_project_reference,
)

PROJECT_NAME_REQUIRED = (
    'Could you please tell me the project name '
    'so I can share the bank details?'
)

class BankDetailsProjectResolutionError(ValueError):
    pass

@dataclass(frozen=True)
class ResolvedBankDetailsProject:
    project_id: str
    project_name: str


def resolve_bank_details_project(
    *,
    message: str,
    snapshot,
    confirmed_project_name: str | None = None,
) -> ResolvedBankDetailsProject:
    projects = {
        p.project_name: str(p.project_id)
        for p in snapshot.projects
        if p.project_id and p.project_name
    }

    # Explicitly confirmed project choices originate in the authenticated
    # session's pending-selection state and are rechecked in the CURRENT live
    # authorized project catalog, not taken from any router-provided name.
    if confirmed_project_name is not None:
        exact = [
            name for name in projects
            if name.casefold() == confirmed_project_name.strip().casefold()
        ]
        if len(exact) != 1:
            raise BankDetailsProjectResolutionError(PROJECT_NAME_REQUIRED)
        return ResolvedBankDetailsProject(
            project_id=projects[exact[0]],
            project_name=exact[0],
        )

    result = match_project_in_message(message, projects)
    if result.status == 'ambiguous':
        raise BankDetailsProjectResolutionError(
            'Multiple projects match your request. Please confirm the project name: '
            + ', '.join(result.candidates[:5])
        )

    if result.status != 'matched' or not result.name:
        raise BankDetailsProjectResolutionError(PROJECT_NAME_REQUIRED)

    return ResolvedBankDetailsProject(
        project_id=projects[result.name],
        project_name=result.name,
    )
