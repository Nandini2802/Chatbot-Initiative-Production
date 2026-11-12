
import logging

from app.schemas.handler_result import HandlerResult
from app.services.walkthrough_access_service import (
    WalkthroughEngine,
    granted_feature_keys,
    norm,
)
from app.services.how_to_video_service import (
    HowToVideoService,
)
from app.services.how_to_video_selector import (
    select_relevant_videos,
)
from app.services.template_service import (
    TemplateService,
)
from app.services.walkthrough_feature_resolver import (
    decide_walkthrough,
    find_walkthrough_candidates,
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
        message: str | None = None,
        llm_client=None,
        llm_model: str = "",
    ):
        self.engine = engine
        self.key_features = key_features
        self.role = role
        self.message = message
        self.llm_client = llm_client
        self.llm_model = llm_model

        self.video_service = HowToVideoService(
            redis_client
        )

        self.templates = TemplateService()

    async def handle(self, intent) -> HandlerResult:

        router_feature = getattr(
            intent,
            "feature_name",
            None,
        )

        # Which walkthrough does the user mean? Router pick + aliases +
        # typo-tolerant match, then decided by the user's access.
        names = [guide.name for guide in self.engine.guides.values()]
        text = (
            self.message
            or getattr(intent, "original_query", None)
            or ""
        )

        candidates = find_walkthrough_candidates(
            text,
            router_feature,
            names,
        )

        decision = decide_walkthrough(
            candidates,
            lambda name: self.engine.permission(
                name=name,
                key_features=self.key_features,
            )[0],
        )

        logger.info(
            "WALKTHROUGH_RESOLVED | router_feature=%s | candidates=%s | "
            "decision=%s | feature=%s | options=%s",
            router_feature,
            candidates,
            decision.kind,
            decision.feature,
            decision.options,
        )

        if decision.kind == "none":
            return HandlerResult(
                intent="excel_walkthrough",
                messages=[WALKTHROUGH_FALLBACK],
            )

        if decision.kind == "ask":
            return HandlerResult(
                intent="excel_walkthrough",
                messages=[decision.message],
            )

        if decision.kind == "denied":
            logger.info(
                "WALKTHROUGH_ACCESS_DENIED | "
                "feature=%s | reason=feature_key_not_granted | "
                "required=%s | granted=%s",
                decision.feature,
                self.engine.required_keys(decision.feature),
                sorted(granted_feature_keys(self.key_features)),
            )

            return HandlerResult(
                intent="excel_walkthrough",
                messages=[decision.message],
            )

        feature_name = decision.feature

        # First authorize the Excel walkthrough.
        result = self.engine.lookup(
            feature=feature_name,
            key_features=self.key_features,
        )

        if result["status"] != "ok":

            # Feature key names are not secret; logging both sides
            # shows immediately whether a denial is a key mismatch.
            logger.info(
                "WALKTHROUGH_ACCESS_DENIED | "
                "feature=%s | reason=%s | required=%s | granted=%s",
                feature_name,
                result.get("reason"),
                self.engine.required_keys(feature_name),
                sorted(granted_feature_keys(self.key_features)),
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

            # Every video the user may watch; the LLM keeps only the
            # one or two whose titles fit the question.
            permitted = await self.video_service.find_permitted_videos(
                key_features=self.key_features,
                role=self.role,
            )

            videos = await select_relevant_videos(
                question=text,
                feature_name=guide.name,
                videos=permitted,
                client=self.llm_client,
                model=self.llm_model,
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
