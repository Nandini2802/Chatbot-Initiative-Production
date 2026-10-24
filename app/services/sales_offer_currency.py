
import json
from decimal import Decimal, InvalidOperation

from app.persistence.redis_store import RedisCacheKeys


class SalesOfferCurrencyError(Exception):
    pass


async def resolve_sales_offer_currency(
    redis_client,
    currency_code: str,
) -> tuple[str, str]:

    # Default currency
    currency_code = (currency_code or "AED").strip().upper()

    # Read existing currency cache
    raw = await redis_client.get(
        RedisCacheKeys.CURRENCY_RATES
    )

    print("\n========== SALES OFFER CURRENCY DEBUG ==========")
    print("Redis key:", RedisCacheKeys.CURRENCY_RATES)
    print("Raw Redis data type:", type(raw).__name__)
    print("Raw Redis data length:", len(raw) if raw is not None else None)

    if raw is None:
        raise SalesOfferCurrencyError(
            "Currency rates are temporarily unavailable."
        )

    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        payload = (
            json.loads(raw)
            if isinstance(raw, str)
            else raw
        )

        print("Parsed payload type:", type(payload).__name__)

        if isinstance(payload, dict):
            print("Top-level keys:", list(payload.keys()))
            print("Top-level base:", repr(payload.get("base")))
            print("Top-level rates present:", isinstance(payload.get("rates"), dict))

            nested_data = payload.get("data")

            print("Nested data type:", type(nested_data).__name__)

            if isinstance(nested_data, dict):
                print("Nested data keys:", list(nested_data.keys()))
                print("Nested base:", repr(nested_data.get("base")))
                print(
                    "Nested rates present:",
                    isinstance(nested_data.get("rates"), dict),
                )

        if not isinstance(payload, dict):
            raise ValueError("Invalid currency payload")

        # Actual API structure:
        # {
        #   "data": {
        #       "base": "AED",
        #       "rates": {
        #           "AED": 1,
        #           "INR": 25.85,
        #           "USD": 0.27
        #       }
        #   },
        #   "metaData": {...}
        # }

        data = payload

        if isinstance(data, dict) and "refreshed_at" in data:
            data = data.get("data", {})

        if isinstance(data, dict) and "data" in data:
            data = data.get("data", {})

        if not isinstance(data, dict):
            raise ValueError("Invalid currency data")

        base = str(data.get("base", "")).upper()

        if base != "AED":
            raise SalesOfferCurrencyError(
                "Unsupported currency base."
            )

        rates = data.get("rates")

        if not isinstance(rates, dict):
            raise ValueError("Currency rates missing")

        if currency_code not in rates:
            raise SalesOfferCurrencyError(
                f"{currency_code} is not available "
                "in the currency rate list."
            )

        rate = Decimal(str(rates[currency_code]))

        if not rate.is_finite() or rate <= 0:
            raise ValueError("Invalid exchange rate")

        return currency_code, str(rate)

    except SalesOfferCurrencyError:
        raise

    except (
        ValueError,
        TypeError,
        InvalidOperation,
    ) as exc:
        raise SalesOfferCurrencyError(
            "Unable to read valid currency rates from Redis."
        ) from exc
