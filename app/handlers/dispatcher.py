from app.schemas.handler_result import HandlerResult
from app.schemas.retrieval import InventorySnapshot

from app.handlers.marketing_handler import MarketingHandler
from app.handlers.inventory_handler import InventoryHandler
from app.handlers.payment_plan_handler import PaymentPlanHandler
from app.handlers.availability_handler import AvailabilityHandler
from app.handlers.bank_details_handler import BankDetailsHandler
from app.handlers.sales_offer_handler import SalesOfferHandler

class IntentDispatcher:

    def __init__(
        self,
        redis_client,
        inventory_snapshot: InventorySnapshot | None = None,
        payment_client=None,
        payment_token: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        access_token: str | None = None,
        message: str = "",
    ):

        self.handlers = {
            "marketing": MarketingHandler(redis_client),
        }

        self.redis_client = redis_client
        self.session_id = session_id

        self.payment_plan_handler = None

        if inventory_snapshot is not None:

            inventory_handler = InventoryHandler(
                inventory_snapshot,
                payment_client=payment_client,
                payment_token=payment_token,
                user_id=user_id,
            )

            self.handlers["inventory"] = inventory_handler

            self.handlers["project_information"] = (
                inventory_handler
            )

            if (
                payment_client is not None
                and payment_token
                and user_id
            ):
                self.payment_plan_handler = PaymentPlanHandler(
                    snapshot=inventory_snapshot,
                    salesforce_client=payment_client,
                    token=payment_token,
                    user_id=user_id,
                    redis_client=redis_client,
                    session_id=session_id,
                )

            if access_token and user_id:
                self.handlers["bank_details"] = BankDetailsHandler(
                    inventory_snapshot=inventory_snapshot,
                    access_token=access_token,
                    user_id=user_id,
                )

            if access_token and user_id and session_id:
                self.handlers["sales_offer"] = SalesOfferHandler(
                    inventory_snapshot=inventory_snapshot,
                    redis_client=redis_client,
                    access_token=access_token,
                    user_id=user_id,
                    session_id=str(session_id),
                    message=message,
                )

        if (
            inventory_snapshot is not None
            and access_token
            and user_id
        ):
            self.handlers["download_availability"] = (
                AvailabilityHandler(
                    redis_client=redis_client,
                    inventory_snapshot=inventory_snapshot,
                    access_token=access_token,
                    user_id=user_id,
                )
            )

    async def execute(self, intent) -> HandlerResult:

        if (
            intent.intent == "inventory"
            and intent.inventory_operation == "payment_plan"
        ):
            if self.payment_plan_handler is None:
                return HandlerResult(
                    intent="inventory",
                    messages=[
                        "The payment plan service "
                        "is currently unavailable."
                    ],
                )

            return await self.payment_plan_handler.handle(
                intent
            )

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
