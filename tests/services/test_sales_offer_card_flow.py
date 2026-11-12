"""
End-to-end check of SalesOfferHandler.generate_sales_offer -> download card.

Only external systems are faked (Salesforce connector, PDF middleware, DB
session, Redis). Everything else is the real code: PDF fetch, local file
save, DB-record creation, card template rendering.
"""
import base64
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.handlers.sales_offer_handler as soh
import app.services.sales_offer_download_service as dls
import app.services.sales_offer_local_storage as store

PDF = b"%PDF-1.4\nhello\n%%EOF\n"


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def delete(self, key):
        self.data.pop(key, None)


class FakeDB:
    def __init__(self, fail_flush=False):
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.fail_flush = fail_flush

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        if self.fail_flush:
            raise RuntimeError('relation "sales_offer_documents" does not exist')

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def fake_http(content, content_type, status=200):
    class FakeSession:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            def raise_for_status():
                if status >= 400:
                    raise RuntimeError(f"HTTP {status}")

            return SimpleNamespace(
                status_code=status,
                headers={"Content-Type": content_type},
                content=content,
                text=content.decode("latin1"),
                raise_for_status=raise_for_status,
                json=lambda: json.loads(content),
            )

    return FakeSession


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("CHATBOT_PUBLIC_BASE_URL", "https://uat.example.net")
    monkeypatch.setattr(store, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(
        dls, "settings",
        SimpleNamespace(sales_offer_download_api="https://mw.example/pdf"),
    )
    monkeypatch.setattr(dls, "CurlAsyncSession", fake_http(PDF, "application/pdf"))

    async def fake_currency(redis, code):
        return code, 1

    monkeypatch.setattr(soh, "resolve_sales_offer_currency", fake_currency)
    return tmp_path


def make_handler(db):
    unit = SimpleNamespace(
        unit_id="U1", unit_name="GRZ-TH-188", project_name="GREENZ BY DANUBE"
    )
    h = soh.SalesOfferHandler(
        inventory_snapshot=SimpleNamespace(units=[unit]),
        redis_client=FakeRedis(),
        access_token="tok",
        user_id="u1",
        session_id=str(uuid.uuid4()),
        message="Selected payment plans",
        db_session=db,
    )

    async def get_unit_details(**kw):
        return SimpleNamespace(
            unitName="GRZ-TH-188",
            payPlanList=[SimpleNamespace(payPlanId="P1"),
                         SimpleNamespace(payPlanId="P2")],
            offerDetails=[],
        )

    async def generate(**kw):
        return [
            SimpleNamespace(salesOfferDocId="D1", salesOfferName="Offer A.pdf"),
            SimpleNamespace(salesOfferDocId="D2", salesOfferName="Offer B.pdf"),
        ]

    h.connector = SimpleNamespace(get_unit_details=get_unit_details,
                                  generate=generate)
    return h


PENDING = {"unit_id": "U1", "unit_name": "GRZ-TH-188",
           "project_name": "GREENZ BY DANUBE", "currency": "AED"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,ctype",
    [
        (PDF, "application/pdf"),
        (base64.b64encode(PDF), "text/plain"),
        (json.dumps({"base64": base64.b64encode(PDF).decode()}).encode(),
         "application/json"),
    ],
    ids=["raw-pdf", "base64", "json"],
)
async def test_download_cards_are_created(env, monkeypatch, content, ctype):
    monkeypatch.setattr(dls, "CurlAsyncSession", fake_http(content, ctype))
    db = FakeDB()
    result = await make_handler(db).generate_sales_offer(PENDING, ["P1", "P2"])

    assert result.generation_context["generated"] is True
    # one card per generated document
    assert [b["card_type"] for b in result.html_blocks] == ["sales_offer_file"] * 2
    assert "https://uat.example.net/api/v1/sales-offer/download/" in result.html_blocks[0]["html"]
    assert "Offer A.pdf" in result.html_blocks[0]["html"]
    # real PDFs were written and DB records created
    assert len(list(Path(env).glob("*.pdf"))) == 2
    assert len(db.added) == 2 and db.committed


# ---------------------------------------------------------------------------
# Failure handling: never claim success when no download card exists.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["api-not-configured", "db-table-missing"]
)
async def test_all_downloads_fail_reports_plainly(env, monkeypatch, caplog, case):
    db = FakeDB(fail_flush=(case == "db-table-missing"))
    if case == "api-not-configured":
        monkeypatch.setattr(
            dls, "settings", SimpleNamespace(sales_offer_download_api="")
        )

    with caplog.at_level("ERROR"):
        result = await make_handler(db).generate_sales_offer(
            PENDING, ["P1", "P2"]
        )

    # No false success
    assert result.html_blocks == []
    assert result.generation_context.get("generated") is not True

    # User sees a plain message only - no technical details
    text = " ".join(result.messages)
    assert text == (
        "I generated the sales offer, but I couldn't prepare "
        "the download. Please try again in a few minutes."
    )

    # The technical reason is in the log
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "SALES_OFFER_DOWNLOAD_ALL_FAILED" in logged
    expected = (
        "SALES_OFFER_DOWNLOAD_API is not configured"
        if case == "api-not-configured"
        else "sales_offer_documents"
    )
    assert expected in logged


@pytest.mark.asyncio
async def test_success_still_returns_cards_no_message(env, monkeypatch):
    result = await make_handler(FakeDB()).generate_sales_offer(
        PENDING, ["P1", "P2"]
    )
    assert len(result.html_blocks) == 2
    assert result.messages == []
    assert result.generation_context["generated"] is True
