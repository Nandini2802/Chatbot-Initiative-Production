
import logging

from app.schemas.handler_result import HandlerResult
from app.services.walkthrough_access_service import WalkthroughEngine


logger = logging.getLogger(__name__)

WALKTHROUGH_FALLBACK = (
    "Great question! While we don't offer that feature yet, "
    "I'd love to help you explore other features which are "
    "available for you."
)


class WalkthroughHandler:
    """
    Handles Excel walkthroughs using request-scoped
    feature keys instead of role-based Excel RBAC.
    """

    def __init__(
        self,
        engine: WalkthroughEngine,
        key_features: str,
    ):
        self.engine = engine
        self.key_features = key_features

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
                    "Which Danube One feature would you "
                    "like help with?"
                ],
            )

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

        logger.info(
            "WALKTHROUGH_ACCESS_GRANTED | feature=%s",
            feature_name,
        )

        approved_steps = result["steps"]

        # Suggest only features available to this user.
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
            messages=[],
            has_data=True,
        )
