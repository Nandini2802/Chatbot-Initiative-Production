
import re

from app.retrieval.bank_details_connector import (
    BankDetailsConnector,
    BankAccount,
)


class BankDetailsService:

    def __init__(self):
        self.connector = BankDetailsConnector()

    @staticmethod
    def account_type(account: BankAccount) -> str:
        value = account.bankType.lower()

        if value.startswith("escrow"):
            return "escrow"

        if value.startswith("corporate"):
            return "corporate"

        return "other"

    @staticmethod
    def account_index(account: BankAccount) -> int | None:
        match = re.search(
            r"\((\d+)\)",
            account.bankType,
        )
        return int(match.group(1)) if match else None

    async def get_accounts(
        self,
        *,
        project_id: str,
        access_token: str,
        user_id: str,
        account_types: list[str] | None = None,
        bank_id: str | None = None,
        bank_name: str | None = None,
        account_number: str | None = None,
        account_index: int | None = None,
    ) -> list[BankAccount]:

        accounts = await self.connector.fetch(
            project_id=project_id,
            access_token=access_token,
            user_id=user_id,
        )

        requested_types = {
            value.lower()
            for value in (account_types or [])
        }

        if requested_types:
            accounts = [
                account
                for account in accounts
                if self.account_type(account)
                in requested_types
            ]

        if bank_id:
            accounts = [
                account
                for account in accounts
                if account.bankId == bank_id
            ]

        if bank_name:
            accounts = [
                account
                for account in accounts
                if bank_name.casefold()
                in account.bankName.casefold()
            ]

        if account_number:
            accounts = [
                account
                for account in accounts
                if account.accountNumber == account_number
            ]

        if account_index is not None:
            accounts = [
                account
                for account in accounts
                if self.account_index(account)
                == account_index
            ]

        return accounts
