import json
import math
from decimal import Decimal, InvalidOperation


BASE_CURRENCY = "AED"

RATE_FIELDS = (
    "exchange_rate",
    "exchangeRate",
    "conversion_rate",
    "conversionRate",
    "rate",
    "value",
)

CODE_FIELDS = (
    "currency_code",
    "currencyCode",
    "code",
)

WRAPPER_FIELDS = (
    "data",
    "rates",
    "currencies",
    "currencyRates",
)


class CurrencyRateError(ValueError):
    pass


def _decimal_rate(value):
    if isinstance(value, bool):
        return None

    if isinstance(value, dict):
        for field in RATE_FIELDS:
            if field in value:
                return _decimal_rate(value[field])
        return None

    if not isinstance(value, (str, int, float, Decimal)):
        return None

    try:
        rate = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None

    if not rate.is_finite() or rate <= 0:
        return None

    return rate


def _decode(payload):
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")

    if isinstance(payload, str):
        payload = json.loads(payload)

    return payload


def _unwrap(payload):
    payload = _decode(payload)

    for _ in range(8):
        if not isinstance(payload, dict):
            break

        explicit_base = (
            payload.get("base_currency")
            or payload.get("baseCurrency")
            or payload.get("base")
        )

        if explicit_base:
            if str(explicit_base).upper() != BASE_CURRENCY:
                raise CurrencyRateError(
                    "Currency rates are not AED-based."
                )

        next_payload = None

        for field in WRAPPER_FIELDS:
            if field in payload:
                next_payload = payload[field]
                break

        if next_payload is None:
            break

        payload = next_payload

    return payload


def extract_exchange_rate(payload, currency: str) -> Decimal:
    """
    Return the number of target-currency units per 1 AED.

    The source API must use AED as its base currency.
    """
    currency = str(currency).strip().upper()

    if len(currency) != 3 or not currency.isalpha():
        raise CurrencyRateError("Invalid currency code.")

    data = _unwrap(payload)

    rate = None

    if isinstance(data, dict):
        for code, value in data.items():
            if str(code).upper() == currency:
                rate = _decimal_rate(value)
                break

    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue

            code = next(
                (item.get(field) for field in CODE_FIELDS
                 if item.get(field)),
                None,
            )

            if str(code or "").upper() != currency:
                continue

            for field in RATE_FIELDS:
                if field in item:
                    rate = _decimal_rate(item[field])
                    break

            break

    if rate is None:
        raise CurrencyRateError(
            f"No valid exchange rate found for {currency}."
        )

    if currency == BASE_CURRENCY and rate != Decimal("1"):
        raise CurrencyRateError(
            "AED base-currency rate must equal 1."
        )

    return rate


def format_exchange_rate(
    currency: str,
    rate: Decimal,
) -> str | None:
    currency = str(currency).upper()

    if currency == BASE_CURRENCY:
        return None

    return (
        f"Today's Conversion Rate: "
        f"AED 1 = {currency} {rate:.5f}"
    )