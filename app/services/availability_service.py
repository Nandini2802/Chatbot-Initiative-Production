
import json

from app.persistence.redis_store import RedisCacheKeys
from app.services.availability_resolver import (
    resolve_availability_project,
)
from app.retrieval.availability_connector import (
    AvailabilityConnector,
)


DISCLAIMER = (
    "Disclaimer: Exchange rate applied is valid "
    "for today only and subject to change at the "
    "time of unit booking."
)


class AvailabilityValidationError(ValueError):
    pass


def extract_currency_codes(payload) -> set[str]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")

    if isinstance(payload, str):
        payload = json.loads(payload)

    if isinstance(payload, dict):
        for key in (
            "data",
            "currencies",
            "currencyRates",
            "rates",
        ):
            if key in payload:
                return extract_currency_codes(payload[key])

        # Dictionary keyed by currency code
        if payload and all(
            isinstance(key, str)
            and len(key) == 3
            and key.isalpha()
            for key in payload
        ):
            return {key.upper() for key in payload}

        return set()

    if isinstance(payload, list):
        codes = set()

        for item in payload:
            if isinstance(item, str):
                codes.add(item.upper())

            elif isinstance(item, dict):
                code = (
                    item.get("currency_code")
                    or item.get("currencyCode")
                    or item.get("code")
                )
                if code:
                    codes.add(str(code).upper())

        return codes

    return set()


class AvailabilityService:

    def __init__(self, redis_client, snapshot):
        self.redis = redis_client
        self.snapshot = snapshot
        self.connector = AvailabilityConnector()

    async def generate(
        self,
        *,
        intent,
        access_token: str,
        user_id: str,
    ) -> dict:

        # 1. Validate file format
        file_type = (
            intent.file_format or "pdf"
        ).strip().lower()

        aliases = {
            "xlsx": "excel",
            "xls": "excel",
            "spreadsheet": "excel",
        }

        file_type = aliases.get(
            file_type, file_type
        )

        if file_type not in {"pdf", "excel"}:
            raise AvailabilityValidationError(
                "Please choose PDF or Excel."
            )

        # 2. Validate currency against Redis
        currency = (
            intent.currency or "AED"
        ).strip().upper()

        cached = await self.redis.get(
            RedisCacheKeys.CURRENCY_RATES
        )
        

        if cached is None:
            raise AvailabilityValidationError(
                "Currency information is temporarily "
                "unavailable. Please try again."
            )

        try:
            supported = extract_currency_codes(cached)
        except (ValueError, TypeError) as exc:
            raise AvailabilityValidationError(
                "Currency information could not "
                "be validated."
            ) from exc

        if not supported:
            raise AvailabilityValidationError(
                "Currency information is unavailable."
            )

        if currency not in supported:
            raise AvailabilityValidationError(
                f"{currency} is not a supported currency. "
                "Please select a valid currency."
            )

        # 3. Resolve project ID
        project = resolve_availability_project(
            intent=intent,
            snapshot=self.snapshot,
        )

        # 4. Call middleware
        report = await self.connector.download(
            project_id=project.project_id,
            currency=currency,
            file_type=file_type,
            access_token=access_token,
            user_id=user_id,
        )

        # 5. Return verified response
        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "currency": currency,
            "file_type": file_type,
            "file_name": report.file_name,
            "file_url": report.file_url,
            "total_records": report.total_records,
            "disclaimer": DISCLAIMER,
        }
