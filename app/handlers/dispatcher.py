from app.schemas.handler_result import HandlerResult
from app.schemas.retrieval import InventorySnapshot

from app.handlers.marketing_handler import MarketingHandler
from app.handlers.inventory_handler import InventoryHandler


class IntentDispatcher:

    def __init__(
        self,
        redis_client,
        inventory_snapshot: InventorySnapshot | None = None,
    ):

        # Register handlers that are always available.
        self.handlers = {
            "marketing": MarketingHandler(redis_client),
        }

        # Register inventory handlers only when
        # an inventory snapshot is available.
        if inventory_snapshot is not None:

            inventory_handler = InventoryHandler(
                inventory_snapshot
            )

            self.handlers["inventory"] = inventory_handler

            self.handlers["project_information"] = (
                inventory_handler
            )

    async def execute(self, intent) -> HandlerResult:

        handler = self.handlers.get(intent.intent)

        if handler is not None:
            return await handler.handle(intent)

        if intent.intent == "out_of_scope":
            return HandlerResult(
                intent="out_of_scope",
                messages=[
                    "I can help with Danube Properties "
                    "projects and related services."
                ],
            )

        return HandlerResult(
            intent=intent.intent,
            messages=[
                "The requested "
                f"{intent.intent.replace('_', ' ')} "
                "service is not available yet."
            ],
        )