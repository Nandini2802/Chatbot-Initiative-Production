
from app.schemas.handler_result import HandlerResult
from app.handlers.marketing_handler import MarketingHandler


class IntentDispatcher:

    def __init__(self, redis_client):

        self.handlers = {
            "marketing": MarketingHandler(redis_client),
        }

    async def execute(self, intent) -> HandlerResult:

        handler = self.handlers.get(intent.intent)

        if handler is not None:
            return await handler.handle(intent)

        # Existing out-of-scope behavior
        if intent.intent == "out_of_scope":
            return HandlerResult(
                intent="out_of_scope",
                messages=[
                    "I can help with Danube Properties "
                    "projects and related services."
                ],
            )

        # Existing placeholder behavior for
        # functionalities not yet integrated
        return HandlerResult(
            intent=intent.intent,
            messages=[
                "The requested "
                f"{intent.intent.replace('_', ' ')} "
                "service is not available yet."
            ],
        )
