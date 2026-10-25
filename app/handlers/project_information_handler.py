
import logging
import re
from urllib.parse import urlparse

from app.schemas.handler_result import HandlerResult
from app.retrieval.project_information_connector import (
    ProjectInformationConnector,
    ProjectInformationAPIError,
)
from app.services.template_service import TemplateService

logger = logging.getLogger(__name__)


def normalize(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value or "").casefold(),
    )


def safe_image_url(url):
    if not isinstance(url, str):
        return None

    parsed = urlparse(url)

    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
    ):
        return None

    # Only render images from approved project-image hosts.
    allowed_hosts = {
        "danubeproperties.com",
        "www.danubeproperties.com",
    }

    return (
        url if parsed.hostname in allowed_hosts
        else None
    )


class ProjectInformationHandler:

    def __init__(
        self,
        *,
        inventory_snapshot,
        inventory_token: str,
        access_token: str,
    ):
        self.snapshot = inventory_snapshot
        self.inventory_token = inventory_token
        self.access_token = access_token
        self.connector = ProjectInformationConnector()
        self.templates = TemplateService()

    def failure(self, message):
        return HandlerResult(
            intent="project_information",
            messages=[message],
            has_data=False,
        )

    def resolve_project(self, intent, projects):
        identifiers = [
            ("project_id", intent.project_id),
            ("project_number", intent.project_number),
            ("project_name", intent.project_name),
        ]

        candidate_sets = []

        for field, value in identifiers:
            if not value:
                continue

            key = normalize(value)

            exact = [
                project
                for project in projects
                if normalize(getattr(project, field, None))
                == key
            ]

            # Permit unique shortened project names.
            if not exact and field == "project_name":
                exact = [
                    project
                    for project in projects
                    if key in normalize(project.project_name)
                ]

            if not exact:
                return None, "Project not found."

            candidate_sets.append({
                project.project_id
                for project in exact
            })

        unit_identifiers = [
            intent.unit_id,
            intent.unit_name,
            intent.unit_number,
        ]

        if any(unit_identifiers):
            matched_units = []

            for unit in self.snapshot.units:
                values = [
                    unit.unit_id,
                    unit.unit_name,
                    unit.unit_code,
                ]

                if any(
                    normalize(identifier) == normalize(value)
                    for identifier in unit_identifiers
                    if identifier
                    for value in values
                    if value
                ):
                    matched_units.append(unit)

            if not matched_units:
                return None, (
                    "I couldn't find that unit in your "
                    "authorized inventory."
                )

            candidate_sets.append({
                unit.project_id
                for unit in matched_units
                if unit.project_id
            })

        if not candidate_sets:
            return None, (
                "Please specify a project name, "
                "number, ID, or unit."
            )

        matching_ids = set.intersection(*candidate_sets)

        matches = [
            project
            for project in projects
            if project.project_id in matching_ids
        ]

        if len(matches) == 1:
            return matches[0], None

        if len(matches) > 1:
            return None, (
                "Multiple projects match your request. "
                "Please specify the exact project."
            )

        return None, (
            "No project matches the supplied identifiers."
        )

    @staticmethod
    def project_summary(project):
        return {
            "project_name": project.project_name,
            "project_id": project.project_id,
            "project_number": project.project_number,
            "location": project.location,
            "starting_price_aed": project.starting_price,
            "total_units": project.total_units,
            "bedrooms": project.bedrooms_categories,
            "apartments": project.apartments,
            "payment_plan": project.payment_plan,
            "construction_status": project.construction_status,
            "handover_date": project.handover_date,
            "completion_date": project.completion_date,
            "project_configuration": (
                project.project_configuration
            ),
            "service_charge": project.service_charge,
            "amenities": project.amenities,
            "places_nearby": project.places_nearby,
        }

    def render_cards(self, projects):
        cards = []

        for project in projects:
            html = self.templates.render(
                "project_information_card.html.j2",
                project_name=project.project_name,
                image_url=safe_image_url(
                    project.project_image
                ),
                starting_price=project.starting_price,
                total_units=project.total_units,
                location=project.location,
            )

            cards.append({
                "card_type": "project_information",
                "html": html,
            })

        return cards

    async def handle(self, intent):
        try:
            projects = await self.connector.fetch_projects(
                inventory_token=self.inventory_token,
                access_token=self.access_token,
            )

            projects = [
                project
                for project in projects
                if project.project_id and project.project_name
            ]

            operation = intent.project_operation or "details"

            if operation == "latest":
                limit = min(
                    max(intent.project_limit or 3, 1),
                    20,
                )
                selected = projects[:limit]

            elif operation == "list":
                limit = min(
                    max(intent.project_limit or 5, 1),
                    20,
                )
                selected = projects[:limit]

            elif operation == "location_search":
                location = normalize(intent.project_location)

                if not location:
                    return self.failure(
                        "Which location would you like "
                        "to search?"
                    )

                selected = [
                    project
                    for project in projects
                    if location in normalize(project.location)
                ][:20]

            else:
                project, error = self.resolve_project(
                    intent,
                    projects,
                )

                if error:
                    return self.failure(error)

                selected = [project]

            if not selected:
                return self.failure(
                    "No matching Danube projects were found."
                )

            summaries = [
                self.project_summary(project)
                for project in selected
            ]

            return HandlerResult(
                intent="project_information",
                html_blocks=self.render_cards(selected),
                files=[],
                messages=[],
                generation_context={
                    "service": "project_information",
                    "operation": operation,
                    "result_count": len(selected),
                    "requested_location": (
                        intent.project_location
                    ),
                    "projects": summaries,
                },
                has_data=True,
            )

        except ProjectInformationAPIError:
            logger.exception(
                "PROJECT_INFORMATION_FETCH_FAILED"
            )
            return self.failure(
                "Project information is temporarily "
                "unavailable. Please try again."
            )
