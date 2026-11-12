
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

    @staticmethod
    def format_account_type(bank_type: str) -> str:
        """Convert API bank type into a user-friendly label."""
        value = (bank_type or "").strip()

        match = re.fullmatch(
            r"(escrow|corporate)\s*\(\s*(\d+)\s*\)",
            value,
            flags=re.IGNORECASE,
        )

        if match:
            account_type = match.group(1).capitalize()
            account_number = match.group(2)
            return f"{account_type} Account {account_number}"

        return value

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

        return self.filter_accounts(
            accounts,
            account_types=account_types,
            bank_id=bank_id,
            bank_name=bank_name,
            account_number=account_number,
            account_index=account_index,
        )

    async def get_accounts_with_type_fallback(
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
    ) -> tuple[list[BankAccount], bool]:
        """
        Same as get_accounts (one API call), but when only an account
        TYPE was requested and the project has none of that type
        (e.g. escrow asked, only corporate exists), return the project's
        other accounts instead.

        Returns (accounts, requested_type_found).
        """

        accounts = await self.connector.fetch(
            project_id=project_id,
            access_token=access_token,
            user_id=user_id,
        )

        matched = self.filter_accounts(
            accounts,
            account_types=account_types,
            bank_id=bank_id,
            bank_name=bank_name,
            account_number=account_number,
            account_index=account_index,
        )

        specific_account_requested = any([
            bank_id,
            bank_name,
            account_number,
            account_index is not None,
        ])

        if matched or not account_types or specific_account_requested:
            return matched, True

        return accounts, False

    def filter_accounts(
        self,
        accounts: list[BankAccount],
        *,
        account_types: list[str] | None = None,
        bank_id: str | None = None,
        bank_name: str | None = None,
        account_number: str | None = None,
        account_index: int | None = None,
    ) -> list[BankAccount]:

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
