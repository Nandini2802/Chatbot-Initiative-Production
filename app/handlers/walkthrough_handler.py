
import logging

from app.schemas.handler_result import HandlerResult
from app.services.walkthrough_access_service import (
    WalkthroughEngine,
    norm,
)
from app.services.how_to_video_service import (
    HowToVideoService,
)
from app.services.template_service import (
    TemplateService,
)


logger = logging.getLogger(__name__)

WALKTHROUGH_FALLBACK = (
    "Great question! While we don't offer that feature yet, "
    "I'd love to help you explore other features which are "
    "available for you."
)


class WalkthroughHandler:

    def __init__(
        self,
        engine: WalkthroughEngine,
        key_features: str | None,
        role: str,
        redis_client,
    ):
        self.engine = engine
        self.key_features = key_features
        self.role = role

        self.video_service = HowToVideoService(
            redis_client
        )

        self.templates = TemplateService()

    async def handle(self, intent) -> HandlerResult:

        feature_name = getattr(
            intent,
            "feature_name",
            None,
        )

        if not feature_name:
            return HandlerResult(
                intent="excel_walkthrough",
                messages=[
                    "Which Danube One feature would "
                    "you like help with?"
                ],
            )

        # First authorize the Excel walkthrough.
        result = self.engine.lookup(
            feature=feature_name,
            key_features=self.key_features,
        )

        if result["status"] != "ok":

            logger.info(
                "WALKTHROUGH_ACCESS_DENIED | "
                "feature=%s | reason=%s",
                feature_name,
                result.get("reason"),
            )

            return HandlerResult(
                intent="excel_walkthrough",
                messages=[WALKTHROUGH_FALLBACK],
            )

        approved_steps = result["steps"]

        # Existing authorized follow-up suggestions.
        allowed_followup_features = []

        for guide in self.engine.guides.values():

            if guide.name == result["feature"]:
                continue

            allowed, _ = self.engine.permission(
                name=guide.name,
                key_features=self.key_features,
            )

            if allowed:
                allowed_followup_features.append(
                    guide.name
                )

        # Video is optional; it must never block steps.
        html_blocks = []

        try:
            guide = self.engine.guides[
                norm(result["feature"])
            ]

            videos = await self.video_service.find_videos(
                feature_name=guide.name,
                excel_feature_key=guide.key,
                key_features=self.key_features,
                role=self.role,
            )

            if videos:
                html = self.templates.render(
                    "how_to_video.html.j2",
                    videos=videos,
                )

                html_blocks.append({
                    "card_type": "walkthrough_video",
                    "html": html,
                })

                logger.info(
                    "WALKTHROUGH_VIDEO_ATTACHED | "
                    "feature=%s | count=%s",
                    guide.name,
                    len(videos),
                )

        except Exception:
            logger.exception(
                "WALKTHROUGH_VIDEO_LOOKUP_FAILED | "
                "feature=%s",
                result["feature"],
            )

        return HandlerResult(
            intent="excel_walkthrough",
            generation_context={
                "service": "excel_walkthrough",
                "feature_name": result["feature"],
                "approved_steps": approved_steps,
                "allowed_followup_features": (
                    allowed_followup_features
                ),
                "match_status": "exact",
            },
            html_blocks=html_blocks,
            messages=[],
            has_data=True,
        )
