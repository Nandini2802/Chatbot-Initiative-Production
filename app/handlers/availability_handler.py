
from app.schemas.handler_result import HandlerResult
from app.services.availability_service import (
    AvailabilityService,
    AvailabilityValidationError,
)
from app.services.availability_resolver import (
    AvailabilityResolutionError,
)
from app.retrieval.availability_connector import (
    AvailabilityAPIError,
)
from app.services.template_service import TemplateService


class AvailabilityHandler:

    def __init__(
        self,
        redis_client,
        inventory_snapshot,
        access_token: str,
        user_id: str,
    ):
        self.service = AvailabilityService(
            redis_client=redis_client,
            snapshot=inventory_snapshot,
        )
        self.templates = TemplateService()
        self.access_token = access_token
        self.user_id = user_id

    async def handle(self, intent) -> HandlerResult:

        result = HandlerResult(
            intent="download_availability"
        )

        try:
            report = await self.service.generate(
                intent=intent,
                access_token=self.access_token,
                user_id=self.user_id,
            )

        except (
            AvailabilityValidationError,
            AvailabilityResolutionError,
        ) as exc:
            result.messages.append(str(exc))
            return result

        except AvailabilityAPIError:

            result.messages.append(
                "The availability report could not "
                "be generated right now. Please try again."
            )
            return result

        # HTML file card
        html = self.templates.render(
            "availability.html.j2",
            file_name=report["file_name"],
            file_type=report["file_type"],
            currency=report["currency"],
            download_url=report["file_url"],
            disclaimer=report["disclaimer"],
        )

        result.html_blocks.append({
            "card_type": "availability",
            "html": html,
        })

        # Structured file metadata
        result.files.append({
            "name": report["file_name"],
            "type": "availability",
            "format": report["file_type"],
            "download_url": report["file_url"],
            "currency": report["currency"],
            "project_id": report["project_id"],
            "project_name": report["project_name"],
            "total_records": report["total_records"],
            "disclaimer": report["disclaimer"],
        })

        # Verified context for LLM 2
        result.generation_context = {
            "service": "download_availability",
            "project_name": report["project_name"],
            "currency": report["currency"],
            "file_type": report["file_type"],
            "report_generated": True,
            "total_records": report["total_records"],
            "disclaimer": report["disclaimer"],
        }

        result.has_data = True

        return result
