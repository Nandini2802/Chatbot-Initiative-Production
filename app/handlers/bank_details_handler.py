
import logging

from app.schemas.handler_result import HandlerResult
from app.services.template_service import TemplateService
from app.services.bank_details_service import BankDetailsService
from app.services.availability_resolver import (
    resolve_availability_project,
    AvailabilityResolutionError,
)
from app.retrieval.bank_details_connector import BankDetailsAPIError


logger = logging.getLogger(__name__)


class BankDetailsHandler:

    def __init__(
        self,
        inventory_snapshot,
        access_token: str,
        user_id: str,
    ):
        self.inventory_snapshot = inventory_snapshot
        self.access_token = access_token
        self.user_id = user_id
        self.service = BankDetailsService()
        self.templates = TemplateService()

    async def handle(self, intent) -> HandlerResult:

        result = HandlerResult(intent="bank_details")

        try:
            resolved = resolve_availability_project(
                intent,
                self.inventory_snapshot,
            )

            accounts = await self.service.get_accounts(
                project_id=resolved.project_id,
                access_token=self.access_token,
                user_id=self.user_id,
                account_types=intent.bank_account_types,
                bank_id=intent.bank_id,
                bank_name=intent.bank_name,
                account_number=intent.bank_account_number,
                account_index=intent.bank_account_index,
            )

            if not accounts:
                result.messages.append(
                    "No matching bank accounts were found "
                    f"for {resolved.project_name}."
                )
                return result

            html = self.templates.render(
                "bank_details.html.j2",
                project=resolved.project_name,
                accounts=[
                    account.model_dump()
                    for account in accounts
                ],
            )

            result.html_blocks.append({
                "card_type": "bank_details",
                "html": html,
            })

            result.generation_context = {
                "service": "bank_details",
                "project": resolved.project_name,
                "accounts_found": True,
                "account_count": len(accounts),
                "account_types": [
                    account.bankType
                    for account in accounts
                ],
                "bank_names": list({
                    account.bankName
                    for account in accounts
                }),
            }

            result.has_data = True
            return result

        except AvailabilityResolutionError as exc:
            result.messages.append(str(exc))
            return result

        except BankDetailsAPIError:
            logger.exception("BANK_DETAILS_FAILED")
            result.messages.append(
                "Bank details are temporarily unavailable. "
                "Please try again."
            )
            return result
