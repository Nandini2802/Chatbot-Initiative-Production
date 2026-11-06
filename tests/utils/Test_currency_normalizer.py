
import pytest

from app.utils.currency_normalizer import (
    SUPPORTED_CURRENCIES,
    resolve_currency,
    extract_currency_and_format,
)


@pytest.mark.parametrize(
    "message, expected",
    [
        ("INR", "INR"),
        ("inr", "INR"),
        ("India", "INR"),
        ("Indian currency", "INR"),
        ("Indian rupees", "INR"),
        ("rupees", "INR"),
        ("USD", "USD"),
        ("USA", "USD"),
        ("American dollars", "USD"),
        ("AED", "AED"),
        ("UAE", "AED"),
        ("Dubai currency", "AED"),
        ("dirhams", "AED"),
        ("UK", "GBP"),
        ("British pounds", "GBP"),
        ("Japan", "JPY"),
        ("Japanese yen", "JPY"),
        ("Saudi Arabia", "SAR"),
        ("Canadian dollars", "CAD"),
        ("Swiss franc", "CHF"),
        ("South African rand", "ZAR"),
        ("BTC", "BTC"),
        ("XAU", "XAU"),
        ("XYZ", None),
        ("", None),
        (None, None),
    ],
)
def test_currency_resolution(message, expected):
    assert resolve_currency(message) == expected


@pytest.mark.parametrize(
    "message, currency, file_format",
    [
        ("Indian currency and PDF", "INR", "pdf"),
        ("India", "INR", None),
        ("rupees and excel", "INR", "excel"),
        ("USA Excel", "USD", "excel"),
        ("Dubai currency, PDF please", "AED", "pdf"),
        ("British pounds and spreadsheet", "GBP", "excel"),
        ("USD", "USD", None),
        ("PDF", None, "pdf"),
        ("Excel instead", None, "excel"),
        ("XYZ", None, None),
    ],
)
def test_combined_extraction(message, currency, file_format):
    assert extract_currency_and_format(message) == (
        currency,
        file_format,
    )


def test_all_supported_codes():
    for code in SUPPORTED_CURRENCIES:
        assert resolve_currency(code) == code
