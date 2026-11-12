"""
Bank details:
- Escrow requested but the project only has corporate (or vice versa):
  return the accounts that exist (same single API call) and tell the
  response LLM, which says so in its normal reply. Card unchanged.
- Share button removed from the single-account card (Copy stays).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.handlers import bank_details_handler as bh
from app.retrieval.bank_details_connector import BankAccount
from app.services.bank_details_service import BankDetailsService
from app.services.template_service import TemplateService


def account(bank_type, number="111", bank="Emirates NBD"):
    return BankAccount(bankId=f"B-{bank_type}", bankType=bank_type, bankName=bank,
                       beneficiaryName="Danube", accountNumber=number,
                       ibanNumber="AE00", swiftCode="EBIL", branch="Main")


CORPORATE_ONLY = [account("Corporate (1)")]
ESCROW_ONLY = [account("Escrow (1)", "222")]
MIXED = [account("Escrow (1)", "222"), account("Corporate (1)"), account("Corporate (2)", "333")]


class FakeConnector:
    def __init__(self, accounts):
        self.accounts = accounts
        self.calls = 0

    async def fetch(self, **kw):
        self.calls += 1
        return list(self.accounts)


def service(accounts):
    s = BankDetailsService()
    s.connector = FakeConnector(accounts)
    return s


async def fallback(accounts, **kw):
    s = service(accounts)
    result = await s.get_accounts_with_type_fallback(
        project_id="P", access_token="t", user_id="u", **kw)
    return result, s.connector.calls


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escrow_requested_only_corporate_returns_corporate_in_one_call():
    (accounts, found), calls = await fallback(CORPORATE_ONLY, account_types=["escrow"])
    assert [a.bankType for a in accounts] == ["Corporate (1)"]
    assert found is False
    assert calls == 1


@pytest.mark.asyncio
async def test_corporate_requested_only_escrow_returns_escrow():
    (accounts, found), _ = await fallback(ESCROW_ONLY, account_types=["corporate"])
    assert [a.bankType for a in accounts] == ["Escrow (1)"] and found is False


@pytest.mark.asyncio
async def test_requested_type_exists_unchanged():
    (accounts, found), _ = await fallback(MIXED, account_types=["escrow"])
    assert [a.bankType for a in accounts] == ["Escrow (1)"] and found is True


@pytest.mark.asyncio
async def test_no_type_requested_unchanged():
    (accounts, found), _ = await fallback(MIXED)
    assert len(accounts) == 3 and found is True


@pytest.mark.asyncio
@pytest.mark.parametrize("kw", [
    {"account_types": ["escrow"], "account_number": "999"},
    {"account_types": ["escrow"], "account_index": 2},
    {"account_types": ["escrow"], "bank_name": "Other Bank"},
])
async def test_specific_account_requests_are_never_replaced(kw):
    (accounts, found), _ = await fallback(CORPORATE_ONLY, **kw)
    assert accounts == [] and found is True


@pytest.mark.asyncio
async def test_project_without_accounts_stays_empty():
    (accounts, _), _ = await fallback([], account_types=["escrow"])
    assert accounts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kw,expected", [
    ({"account_types": ["escrow"]}, ["Escrow (1)"]),
    ({"account_types": ["corporate"]}, ["Corporate (1)", "Corporate (2)"]),
    ({"account_types": ["corporate"], "account_index": 2}, ["Corporate (2)"]),
    ({}, ["Escrow (1)", "Corporate (1)", "Corporate (2)"]),
])
async def test_get_accounts_behaviour_unchanged(kw, expected):
    s = service(MIXED)
    accounts = await s.get_accounts(project_id="P", access_token="t", user_id="u", **kw)
    assert [a.bankType for a in accounts] == expected


@pytest.mark.asyncio
async def test_get_accounts_does_not_fall_back():
    s = service(CORPORATE_ONLY)
    assert await s.get_accounts(project_id="P", access_token="t", user_id="u",
                                account_types=["escrow"]) == []


# ---------------------------------------------------------------------------
# Handler -> what the response LLM receives
# ---------------------------------------------------------------------------

def handler(monkeypatch, accounts):
    monkeypatch.setattr(bh, "resolve_bank_details_project", lambda **kw: SimpleNamespace(
        project_id="P-GRZ", project_name="GREENZ BY DANUBE"))
    h = bh.BankDetailsHandler(inventory_snapshot=SimpleNamespace(projects=[], units=[]),
                              access_token="t", user_id="u", message="escrow account of greenz")
    h.service = service(accounts)
    return h


def intent(types):
    return SimpleNamespace(project_name="GREENZ BY DANUBE", bank_account_types=types,
                           bank_id=None, bank_name=None, bank_account_number=None,
                           bank_account_index=None)


@pytest.mark.asyncio
async def test_handler_escrow_missing_gives_corporate_and_tells_llm(monkeypatch):
    result = await handler(monkeypatch, CORPORATE_ONLY).handle(intent(["escrow"]))

    assert result.has_data is True
    assert result.messages == []                                 # no fixed "not found" text
    assert [b["card_type"] for b in result.html_blocks] == ["bank_details"]
    ctx = result.generation_context
    assert ctx["requested_type_found"] is False
    assert ctx["requested_account_types"] == ["Escrow"]
    assert ctx["account_types"] == ["Corporate Account 1"]


@pytest.mark.asyncio
async def test_handler_requested_type_found(monkeypatch):
    result = await handler(monkeypatch, MIXED).handle(intent(["escrow"]))
    ctx = result.generation_context
    assert ctx["requested_type_found"] is True and ctx["account_types"] == ["Escrow Account 1"]


@pytest.mark.asyncio
async def test_handler_no_accounts_still_not_found(monkeypatch):
    result = await handler(monkeypatch, []).handle(intent(["escrow"]))
    assert result.has_data is False
    assert result.messages == ["No matching bank accounts were found for GREENZ BY DANUBE."]


# ---------------------------------------------------------------------------
# Card and prompt
# ---------------------------------------------------------------------------

def test_single_card_has_copy_but_no_share():
    html = TemplateService().render(
        "bank_details_single.html.j2", project="GREENZ BY DANUBE",
        account={**account("Corporate (1)").model_dump(), "displayBankType": "Corporate Account 1",
                 "projectName": "GREENZ BY DANUBE", "accountIndex": 1})
    assert "Copy" in html and "bankCopy" in html
    assert "Share" not in html and "bankShare" not in html and "navigator.share" not in html


def test_prompt_has_missing_type_rule():
    prompt = Path("app/prompts/generation_bank_details_v1.md").read_text(encoding="utf-8")
    assert "requested_type_found = false" in prompt
    assert "has no escrow account, so here's its Corporate Account 1" in prompt
