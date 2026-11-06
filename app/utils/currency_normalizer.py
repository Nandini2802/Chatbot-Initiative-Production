
import re
import unicodedata

import pycountry
from babel import Locale
from babel.numbers import get_currency_name, get_territory_currencies


# Currency codes supported by Danube's currency API.
SUPPORTED_CURRENCIES = frozenset("""
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN
BHD BIF BMD BND BOB BRL BSD BTC BTN BWP BYN BZD CAD CDF
CHF CLF CLP CNH CNY COP CRC CUC CUP CVE CZK DJF DKK DOP
DZD EGP ERN ETB EUR FJD FKP GBP GEL GGP GHS GIP GMD GNF
GTQ GYD HKD HNL HRK HTG HUF IDR ILS IMP INR IQD IRR ISK
JEP JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK
LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR
MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN
PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG
SEK SGD SHP SLE SLL SOS SRD SSP STD STN SVC SYP SZL THB
TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES
VND VUV WST XAF XAG XAU XCD XCG XDR XOF XPD XPF XPT YER
ZAR ZMW ZWG ZWL
""".split())


# Explicit business-friendly aliases.
# Do not map ambiguous words such as "dollar" or "rupee"
# without a country or other distinguishing context.
ALIASES = {
    "india": "INR",
    "indian": "INR",
    "indian currency": "INR",
    "indian money": "INR",
    "indian rupee": "INR",
    "indian rupees": "INR",
    "rupee": "INR",
    "rupees": "INR",
    "inr": "INR",

    "usa": "USD",
    "us": "USD",
    "u s": "USD",
    "america": "USD",
    "american": "USD",
    "united states": "USD",
    "united states of america": "USD",
    "american currency": "USD",
    "american dollar": "USD",
    "american dollars": "USD",
    "us dollar": "USD",
    "us dollars": "USD",
    "usd": "USD",

    "uae": "AED",
    "u a e": "AED",
    "dubai": "AED",
    "abu dhabi": "AED",
    "emirates": "AED",
    "emirati": "AED",
    "united arab emirates": "AED",
    "uae currency": "AED",
    "dubai currency": "AED",
    "emirati dirham": "AED",
    "emirati dirhams": "AED",
    "uae dirham": "AED",
    "uae dirhams": "AED",
    "dirham": "AED",
    "dirhams": "AED",
    "aed": "AED",

    "uk": "GBP",
    "u k": "GBP",
    "britain": "GBP",
    "british": "GBP",
    "great britain": "GBP",
    "united kingdom": "GBP",
    "england": "GBP",
    "british pound": "GBP",
    "british pounds": "GBP",
    "pound sterling": "GBP",
    "sterling": "GBP",
    "gbp": "GBP",

    "euro": "EUR",
    "euros": "EUR",
    "european euro": "EUR",
    "eur": "EUR",

    "japan": "JPY",
    "japanese": "JPY",
    "japanese yen": "JPY",
    "yen": "JPY",
    "jpy": "JPY",

    "canada": "CAD",
    "canadian": "CAD",
    "canadian dollar": "CAD",
    "canadian dollars": "CAD",

    "australia": "AUD",
    "australian": "AUD",
    "australian dollar": "AUD",
    "australian dollars": "AUD",

    "saudi": "SAR",
    "saudi arabia": "SAR",
    "saudi riyal": "SAR",
    "saudi riyals": "SAR",

    "qatar": "QAR",
    "qatari": "QAR",
    "qatari riyal": "QAR",

    "kuwait": "KWD",
    "kuwaiti": "KWD",
    "kuwaiti dinar": "KWD",

    "oman": "OMR",
    "omani": "OMR",
    "omani rial": "OMR",

    "bahrain": "BHD",
    "bahraini": "BHD",
    "bahraini dinar": "BHD",

    "pakistan": "PKR",
    "pakistani": "PKR",
    "pakistani rupee": "PKR",

    "nepal": "NPR",
    "nepalese": "NPR",
    "nepali": "NPR",
    "nepalese rupee": "NPR",

    "bangladesh": "BDT",
    "bangladeshi": "BDT",
    "bangladeshi taka": "BDT",

    "sri lanka": "LKR",
    "sri lankan": "LKR",
    "sri lankan rupee": "LKR",

    "singapore": "SGD",
    "singaporean": "SGD",
    "singapore dollar": "SGD",

    "china": "CNY",
    "chinese": "CNY",
    "chinese yuan": "CNY",
    "renminbi": "CNY",
    "yuan": "CNY",

    "hong kong": "HKD",
    "hong kong dollar": "HKD",

    "switzerland": "CHF",
    "swiss": "CHF",
    "swiss franc": "CHF",

    "south africa": "ZAR",
    "south african": "ZAR",
    "south african rand": "ZAR",
    "rand": "ZAR",

    "new zealand": "NZD",
    "new zealand dollar": "NZD",

    "russia": "RUB",
    "russian": "RUB",
    "russian ruble": "RUB",

    "turkey": "TRY",
    "turkiye": "TRY",
    "turkish": "TRY",
    "turkish lira": "TRY",

    "mexico": "MXN",
    "mexican": "MXN",
    "mexican peso": "MXN",

    "brazil": "BRL",
    "brazilian": "BRL",
    "brazilian real": "BRL",

    "thailand": "THB",
    "thai": "THB",
    "thai baht": "THB",

    "malaysia": "MYR",
    "malaysian": "MYR",
    "malaysian ringgit": "MYR",

    "indonesia": "IDR",
    "indonesian": "IDR",
    "indonesian rupiah": "IDR",

    "philippines": "PHP",
    "philippine": "PHP",
    "philippine peso": "PHP",

    "south korea": "KRW",
    "korean won": "KRW",
    "south korean won": "KRW",

    "bitcoin": "BTC",
    "gold": "XAU",
    "silver": "XAG",
}


FORMAT_ALIASES = {
    "pdf": "pdf",
    "excel": "excel",
    "xlsx": "excel",
    "xls": "excel",
    "spreadsheet": "excel",
    "spread sheet": "excel",
}


def _clean(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.casefold().strip()
    value = re.sub(r"[_\-/]", " ", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _build_aliases() -> dict[str, str]:
    candidates: dict[str, set[str]] = {}

    def register(name: str, code: str) -> None:
        if code not in SUPPORTED_CURRENCIES:
            return
        key = _clean(name)
        if key:
            candidates.setdefault(key, set()).add(code)

    # Currency codes and their localized English names.
    for code in SUPPORTED_CURRENCIES:
        register(code, code)

        try:
            currency = pycountry.currencies.get(alpha_3=code)
            if currency is not None:
                register(currency.name, code)
        except (AttributeError, LookupError):
            pass

        try:
            register(get_currency_name(code, locale="en"), code)
        except (ValueError, LookupError):
            pass

    # Country names mapped to their currency.
    # Avoid guessing when a territory has multiple current
    # currencies or the country name is ambiguous.
    for country in pycountry.countries:
        territory = country.alpha_2
        try:
            codes = set(
                get_territory_currencies(
                    territory,
                    tender=True,
                    non_tender=False,
                )
            ) & SUPPORTED_CURRENCIES
        except (ValueError, LookupError):
            continue

        if len(codes) != 1:
            continue

        code = next(iter(codes))
        register(country.name, code)

        if hasattr(country, "official_name"):
            register(country.official_name, code)

        if hasattr(country, "common_name"):
            register(country.common_name, code)

    # Remove ambiguous aliases from automatic resolution.
    result = {
        name: next(iter(codes))
        for name, codes in candidates.items()
        if len(codes) == 1
    }

    # Explicit product aliases take priority.
    for name, code in ALIASES.items():
        if code in SUPPORTED_CURRENCIES:
            result[_clean(name)] = code

    return result


CURRENCY_ALIASES = _build_aliases()


def _matches(text: str, alias: str) -> bool:
    return bool(
        re.search(
            rf"(?<!\w){re.escape(alias)}(?!\w)",
            text,
        )
    )


def resolve_currency(value: str | None) -> str | None:
    """
    Return a supported currency code or None.

    Accepts:
      INR
      Indian currency
      India
      rupees
      in US dollars
      give it in Dubai currency
    """
    if not value or not isinstance(value, str):
        return None

    text = _clean(value)

    if not text:
        return None

    if text.upper() in SUPPORTED_CURRENCIES:
        return text.upper()

    # Match longer phrases before shorter aliases.
    matches = []

    for alias, code in sorted(
        CURRENCY_ALIASES.items(),
        key=lambda pair: len(pair[0]),
        reverse=True,
    ):
        if _matches(text, alias):
            matches.append((alias, code))

    if not matches:
        return None

    # Prefer the longest, most specific alias.
    longest = max(len(alias) for alias, _ in matches)
    best = {
        code
        for alias, code in matches
        if len(alias) == longest
    }

    return next(iter(best)) if len(best) == 1 else None


def extract_currency_and_format(
    message: str,
) -> tuple[str | None, str | None]:
    """
    Extract both values from one natural-language reply.

    Examples:
      'Indian currency and PDF' -> ('INR', 'pdf')
      'USA excel' -> ('USD', 'excel')
      'rupees' -> ('INR', None)
    """
    text = _clean(message)

    file_format = None

    for alias, normalized in FORMAT_ALIASES.items():
        if _matches(text, alias):
            file_format = normalized
            break

    # Remove file-format words before currency resolution.
    currency_text = text

    for alias in sorted(FORMAT_ALIASES, key=len, reverse=True):
        currency_text = re.sub(
            rf"(?<!\w){re.escape(alias)}(?!\w)",
            " ",
            currency_text,
        )

    currency = resolve_currency(currency_text)

    return currency, file_format
