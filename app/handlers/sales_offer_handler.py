
import logging
import re

from app.schemas.handler_result import HandlerResult

from app.handlers.inventory_handler import InventoryHandler

from app.services.template_service import TemplateService
from app.services.sales_offer_state import SalesOfferState

from app.services.sales_offer_resolver import (
    find_project_units,
    find_unit,
    SalesOfferResolutionError,
)

from app.services.sales_offer_plan_selection import (
    select_from_names,
    select_from_text,
    SalesOfferPlanSelectionError,
)

from app.services.sales_offer_currency import (
    resolve_sales_offer_currency,
    SalesOfferCurrencyError,
)

from app.retrieval.sales_offer_connector import (
    SalesOfferConnector,
    SalesOfferAPIError,
)

from app.services.sales_offer_download_service import (
    create_sales_offer_download,
)


logger = logging.getLogger(__name__)


class SalesOfferHandler:

    def __init__(
        self,
        *,
        inventory_snapshot,
        redis_client,
        access_token,
        user_id,
        session_id,
        message,
        selected_payment_plan_names=None,
        db_session,
    ):
        self.snapshot = inventory_snapshot
        self.redis = redis_client
        self.access_token = access_token
        self.user_id = user_id
        self.session_id = str(session_id)
        self.message = message.strip()
        self.db_session = db_session

        self.selected_payment_plan_names = (
            selected_payment_plan_names
        )

        self.connector = SalesOfferConnector()
        self.state = SalesOfferState(redis_client)
        self.templates = TemplateService()
        

    def reply(self, message, html_blocks=None):
        return HandlerResult(
            intent="sales_offer",
            messages=[message],
            html_blocks=html_blocks or [],
            has_data=False,
        )

    async def load(self):
        return await self.state.load(
            user_id=self.user_id,
            session_id=self.session_id,
        )

    async def save(self, data):
        await self.state.save(
            user_id=self.user_id,
            session_id=self.session_id,
            state=data,
        )

    async def clear(self):
        await self.state.clear(
            user_id=self.user_id,
            session_id=self.session_id,
        )

    def authorized_unit(self, unit_id):
        return next(
            (
                unit
                for unit in self.snapshot.units
                if unit.unit_id == unit_id
            ),
            None,
        )

    @staticmethod
    def is_yes(value):
        return value.strip().casefold() in {
            "yes",
            "y",
            "yeah",
            "yep",
            "correct",
            "confirmed",
            "confirm",
            "proceed",
            "go ahead",
            "use this",
            "use this unit",
            "that's correct",
        }

    @staticmethod
    def is_no(value):
        return value.strip().casefold() in {
            "no",
            "n",
            "nope",
            "incorrect",
            "wrong",
            "not this",
            "not this one",
        }

    @staticmethod
    def currency_from_message(message):
        """
        Accept:
        AED
        USD
        INR
        use USD
        in AED
        currency USD
        """

        match = re.fullmatch(
            r"(?:use\s+|in\s+|currency\s+)?"
            r"([a-zA-Z]{3})",
            message.strip(),
            flags=re.IGNORECASE,
        )

        return (
            match.group(1).upper()
            if match
            else None
        )

    @staticmethod
    def unit_from_message(message):
        """
        Accept a direct unit name/ID, or:
        unit GRZ-TH-808
        select GRZ-TH-808
        """

        return re.sub(
            r"^(?:unit|select|choose)\s+",
            "",
            message.strip(),
            flags=re.IGNORECASE,
        ).strip()

    async def ask_currency(self, unit, currency=None):
        """
        Called only after resolving a valid unit.
        Currency is confirmed before payment plans.
        """

        code = (currency or "AED").upper()

        await self.save({
            "stage": "currency_confirmation",
            "unit_id": unit.unit_id,
            "unit_name": unit.unit_name,
            "project_name": unit.project_name,
            "currency": code,
        })

        return self.reply(
            f"Unit {unit.unit_name} in "
            f"{unit.project_name} has been selected. "
            f"Would you like to generate the sales offer "
            f"in {code}? Please confirm, or specify "
            "another currency such as USD or INR."
        )

    async def show_project_units(self, intent):
        """
        Reuse Inventory listing 2.html.j2.
        Do not expose unit IDs in the HTML unless
        the existing template already does so.
        """

        units = find_project_units(
            intent,
            self.snapshot,
        )

        if not units:
            return self.reply(
                "No units were found for that project "
                "in your authorized inventory."
            )

        mapper = InventoryHandler(self.snapshot)

        displayed = units[:mapper.MAX_DISPLAY_UNITS]

        await self.save({
            "stage": "unit_selection",
            "candidate_unit_ids": [
                unit.unit_id
                for unit in units
            ],
            "currency": (
                getattr(intent, "currency", None)
                or "AED"
            ).upper(),
        })

        html = self.templates.render(
            "listing 2.html.j2",
            units=[
                mapper._unit_data(unit)
                for unit in displayed
            ],
            total_matches=len(units),
        )

        return self.reply(
            "Please specify the unit for which "
            "you want to generate the sales offer. "
            "You can type the unit name or ID "
            "from the listing.",
            html_blocks=[
                {
                    "card_type": "inventory_listing",
                    "html": html,
                }
            ],
        )

    async def show_payment_plans(self, pending):
        """
        Called after currency confirmation.

        Fetches fresh getUnitDetails data and
        stores every plan name and ID in Redis.
        """

        unit = self.authorized_unit(
            pending["unit_id"]
        )

        if not unit:
            await self.clear()

            return self.reply(
                "This unit is no longer available "
                "in your authorized inventory."
            )

        details = await self.connector.get_unit_details(
            unit_id=unit.unit_id,
            access_token=self.access_token,
        )

        plans = details.payPlanList or []

        if not plans:
            await self.clear()

            return self.reply(
                f"No payment plans are available "
                f"for unit {details.unitName}."
            )

        mapping = [
            {
                "name": plan.payPlanName,
                "id": plan.payPlanId,
            }
            for plan in plans
        ]

        # Frontend sends names, so each name
        # must identify exactly one plan.
        normalized_names = [
            plan["name"].strip().casefold()
            for plan in mapping
            if plan["name"] and plan["id"]
        ]

        if (
            len(normalized_names) != len(mapping)
            or len(set(normalized_names)) != len(mapping)
        ):
            return self.reply(
                "The payment-plan list contains "
                "missing or duplicate names. "
                "Please contact support."
            )

        pending.update({
            "stage": "payment_plan_selection",
            "unit_name": details.unitName,
            "plans": mapping,
        })

        await self.save(pending)

        # Single payment plan:
        # Automatically use its ID.
        if len(mapping) == 1:
            return await self.generate_sales_offer(
                pending,
                [mapping[0]["id"]],
            )

        # Multiple payment plans:
        # Render the supplied dynamic HTML.
        html = self.templates.render(
            "sales_offer_plans.html.j2",
            unit_name=details.unitName,
            plans=[
                plan.model_dump()
                for plan in plans
            ],
        )

        return self.reply(
            f"Your sales offer is almost ready. Please select your "
            f"preferred payment plan for unit {details.unitName}, "
            "or simply type your preferred payment plan(s) and send.",
            html_blocks=[
                {
                    "card_type": "sales_offer_plans",
                    "html": html,
                }
            ],
        )

    async def generate_sales_offer(
        self,
        pending,
        selected_plan_ids,
    ):
        """
        Flow 2 handoff using the existing connector.
        Revalidates unit, plans and currency.
        """

        unit = self.authorized_unit(
            pending["unit_id"]
        )

        if not unit:
            await self.clear()

            return self.reply(
                "The unit is no longer available "
                "in your authorized inventory."
            )

        details = await self.connector.get_unit_details(
            unit_id=unit.unit_id,
            access_token=self.access_token,
        )

        current_plan_ids = {
            plan.payPlanId
            for plan in details.payPlanList or []
        }

        if (
            not selected_plan_ids
            or len(set(selected_plan_ids))
            != len(selected_plan_ids)
            or any(
                plan_id not in current_plan_ids
                for plan_id in selected_plan_ids
            )
        ):
            await self.clear()

            return self.reply(
                "The selected payment plans are no longer "
                "valid. Please start a new sales offer request."
            )

        # Existing behavior: additional offer selection
        # is not yet supported.
        if details.offerDetails:
            return self.reply(
                "This unit has additional sales offers. "
                "Please select an applicable offer "
                "before generation."
            )

        currency_code, exchange_rate = (
            await resolve_sales_offer_currency(
                self.redis,
                pending["currency"],
            )
        )

        generated = await self.connector.generate(
            unit_id=unit.unit_id,
            unit_name=details.unitName,
            offer_id="",
            payment_plan_ids=selected_plan_ids,
            currency_code=currency_code,
            exchange_rate=exchange_rate,
            access_token=self.access_token,
        )

        if not generated:
            return self.reply(
                "The Sales Offer API did not "
                "return any generated documents."
            )

        document_ids = [
            document.salesOfferDocId
            for document in generated
        ]

        document_names = [
            document.salesOfferName
            for document in generated
        ]



        html_blocks = []
        download_errors = []

        logger.info(
            "FLOW3_GENERATED_DOCUMENTS | count=%s",
            len(generated),
        )

        for document in generated:
            try:
                logger.info(
                    "FLOW3_PROCESSING | document_id=%s",
                    document.salesOfferDocId,
                )

                download = await create_sales_offer_download(
                    db_session=self.db_session,
                    document_id=document.salesOfferDocId,
                    file_name=document.salesOfferName,
                    access_token=self.access_token,
                    user_id=self.user_id,
                    session_id=self.session_id,
                )

                logger.info(
                    "FLOW3_DOWNLOAD_CREATED | size=%s",
                    download["file_size"],
                )

                html = self.templates.render(
                    "sales_offer_file.html.j2",
                    file_name=download["file_name"],
                    file_size=download["file_size"],
                    download_url=download["download_url"],
                )

                html_blocks.append({
                    "card_type": "sales_offer_file",
                    "html": html,
                })

                logger.info(
                    "FLOW3_HTML_BLOCK_CREATED | total=%s",
                    len(html_blocks),
                )

            except Exception:
                logger.exception(
                    "SALES_OFFER_DOWNLOAD_FAILED | "
                    "document_id=%s",
                    document.salesOfferDocId,
                )

                download_errors.append(
                    document.salesOfferName
                )

        logger.info(
            "FLOW3_FINAL_RESULT | html_blocks=%s | "
            "failed_documents=%s",
            len(html_blocks),
            len(download_errors),
        )


        await self.clear()

        return HandlerResult(
            intent="sales_offer",
            messages=[],
            html_blocks=html_blocks,
            generation_context={
                "service": "sales_offer",
                "generated": True,
                "unit_name": details.unitName,
                "project_name": unit.project_name,
                "currency": currency_code,
                "exchange_rate": exchange_rate,
                "exchange_rate_direction": "AED_TO_TARGET",
                "document_count": len(generated),
                "document_ids": document_ids,
                "document_names": document_names,
            },
            has_data=True,
        )

    async def handle(self, intent):
        try:
            pending = await self.load()

            # ----------------------------------
            # 1. PROJECT -> UNIT SELECTION
            # ----------------------------------

            if (
                pending
                and pending.get("stage")
                == "unit_selection"
            ):
                requested = self.unit_from_message(
                    self.message
                )

                unit, needs_confirmation = find_unit(
                    requested,
                    self.snapshot,
                    allowed_unit_ids=pending[
                        "candidate_unit_ids"
                    ],
                )

                if needs_confirmation:
                    await self.save({
                        "stage": "unit_confirmation",
                        "unit_id": unit.unit_id,
                        "unit_name": unit.unit_name,
                        "project_name": unit.project_name,
                        "currency": pending.get(
                            "currency", "AED"
                        ),
                    })

                    return self.reply(
                        f"Are you referring to unit "
                        f"{unit.unit_name} in "
                        f"{unit.project_name}? "
                        "Please confirm yes or no."
                    )

                return await self.ask_currency(
                    unit,
                    pending.get("currency"),
                )

            # ----------------------------------
            # 2. NORMALIZED UNIT CONFIRMATION
            # ----------------------------------

            if (
                pending
                and pending.get("stage")
                == "unit_confirmation"
            ):
                if self.is_no(self.message):
                    await self.clear()

                    return self.reply(
                        "Please specify the unit "
                        "for which you want to "
                        "generate the sales offer."
                    )

                if not self.is_yes(self.message):
                    return self.reply(
                        f"Are you referring to unit "
                        f'{pending["unit_name"]} in '
                        f'{pending["project_name"]}? '
                        "Please reply yes or no."
                    )

                unit = self.authorized_unit(
                    pending["unit_id"]
                )

                if not unit:
                    await self.clear()

                    return self.reply(
                        "This unit is no longer available "
                        "in your authorized inventory."
                    )

                return await self.ask_currency(
                    unit,
                    pending.get("currency"),
                )

            # ----------------------------------
            # 3. CURRENCY CONFIRMATION
            # ----------------------------------

            if (
                pending
                and pending.get("stage")
                == "currency_confirmation"
            ):
                # Check yes/no before parsing currency codes.
                if self.is_no(self.message):
                    return self.reply(
                        "Please specify the currency "
                        "you would like to use."
                    )

                if self.is_yes(self.message):
                    currency = pending.get("currency") or "AED"
                else:
                    currency = self.currency_from_message(self.message)

                    if currency is None:
                        return self.reply(
                            f"Please specify a currency such as AED, "
                            f"USD or INR for unit {pending['unit_name']}."
                        )

                # Read and validate currency from Redis.
                currency_code, exchange_rate = (
                    await resolve_sales_offer_currency(
                        self.redis,
                        currency,
                    )
                )

                pending["currency"] = currency_code
                pending["exchange_rate"] = exchange_rate
                await self.save(pending)

                result = await self.show_payment_plans(pending)

                # Single payment plan:
                # Offer has already been generated.
                if result.generation_context.get("generated") is True:
                    return result

                # Multiple payment plans:
                # Show currency confirmation before selection.
                if pending.get("stage") == "payment_plan_selection":
                    if currency_code == "AED":
                        prefix = (
                            "Perfect, I will generate "
                            "the sales offer in AED."
                        )
                    else:
                        prefix = (
                            f"Perfect, I will generate the sales offer "
                            f"in {currency_code} "
                            f"(based on today's conversion rate: "
                            f"AED 1 = {currency_code} {exchange_rate})."
                        )

                    disclaimer = (
                        "Disclaimer: Exchange rate applied is valid "
                        "for today only and subject to change "
                        "at the time of unit booking."
                    )

                    result.messages.insert(
                        0,
                        f"{prefix}\n\n{disclaimer}",
                    )

                return result


            # ----------------------------------
            # 4. PAYMENT PLAN SELECTION
            # ----------------------------------

            if (
                pending
                and pending.get("stage")
                == "payment_plan_selection"
            ):
                plans = pending["plans"]

                if self.selected_payment_plan_names is not None:
                    selected_ids = select_from_names(
                        self.selected_payment_plan_names,
                        plans,
                    )
                else:
                    selected_ids = select_from_text(
                        self.message,
                        plans,
                    )

                return await self.generate_sales_offer(
                    pending,
                    selected_ids,
                )

            # ----------------------------------
            # 5. NEW SALES OFFER REQUEST
            # ----------------------------------

            requested_unit = (
                getattr(intent, "unit_id", None)
                or getattr(intent, "unit_name", None)
                or getattr(intent, "unit_number", None)
            )

            has_project = any(
                getattr(intent, key, None)
                for key in (
                    "project_id",
                    "project_name",
                    "project_number",
                )
            )

            if not requested_unit:
                if has_project:
                    return await self.show_project_units(
                        intent
                    )

                return self.reply(
                    "Please specify a project or unit "
                    "for the sales offer."
                )

            allowed_unit_ids = None

            if has_project:
                allowed_unit_ids = [
                    unit.unit_id
                    for unit in find_project_units(
                        intent,
                        self.snapshot,
                    )
                ]

            unit, needs_confirmation = find_unit(
                requested_unit,
                self.snapshot,
                allowed_unit_ids=allowed_unit_ids,
            )

            if needs_confirmation:
                await self.save({
                    "stage": "unit_confirmation",
                    "unit_id": unit.unit_id,
                    "unit_name": unit.unit_name,
                    "project_name": unit.project_name,
                    "currency": (
                        getattr(intent, "currency", None)
                        or "AED"
                    ).upper(),
                })

                return self.reply(
                    f"Are you referring to unit "
                    f"{unit.unit_name} in "
                    f"{unit.project_name}? "
                    "Please confirm yes or no."
                )

            return await self.ask_currency(
                unit,
                getattr(intent, "currency", None),
            )

        except (
            SalesOfferResolutionError,
            SalesOfferPlanSelectionError,
            SalesOfferCurrencyError,
        ) as exc:
            return self.reply(str(exc))

        except SalesOfferAPIError:
            logger.exception(
                "SALES_OFFER_API_FAILED"
            )

            return self.reply(
                "The sales offer service is temporarily "
                "unavailable. Please try again."
            )
