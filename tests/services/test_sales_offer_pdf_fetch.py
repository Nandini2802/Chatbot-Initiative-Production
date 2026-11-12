"""
Regression: fetch_sales_offer_pdf crashed with UnboundLocalError
('pdf_bytes') whenever the middleware returned Base64 or JSON instead of
raw PDF bytes, so no download card was shown for generated sales offers.
"""
import base64
import json
from types import SimpleNamespace

import pytest

import app.services.sales_offer_download_service as svc

PDF = b"%PDF-1.4\nhello\n%%EOF\n"
B64 = base64.b64encode(PDF)


def fake_session(content: bytes, content_type: str):
    class FakeSession:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            return SimpleNamespace(
                status_code=200,
                headers={"Content-Type": content_type},
                content=content,
                text=content.decode("latin1"),
                raise_for_status=lambda: None,
                json=lambda: json.loads(content),
            )

    return FakeSession


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,content_type",
    [
        (PDF, "application/pdf"),
        (B64, "text/plain"),
        (json.dumps({"base64": B64.decode()}).encode(), "application/json"),
        (json.dumps({"fileContent": B64.decode()}).encode(), "application/json"),
        (json.dumps(B64.decode()).encode(), "application/json"),
        (b"data:application/pdf;base64," + B64, "text/plain"),
    ],
    ids=["raw", "base64", "json-base64", "json-fileContent",
         "json-string", "data-uri"],
)
async def test_fetch_pdf_all_response_formats(
    monkeypatch, content, content_type
):
    monkeypatch.setattr(
        svc,
        "settings",
        SimpleNamespace(sales_offer_download_api="https://x.example/api"),
    )
    monkeypatch.setattr(
        svc, "CurlAsyncSession", fake_session(content, content_type)
    )

    result = await svc.fetch_sales_offer_pdf(
        document_id="doc-1", access_token="tok", user_id="u"
    )

    assert result == PDF


@pytest.mark.asyncio
async def test_fetch_pdf_rejects_non_pdf(monkeypatch):
    monkeypatch.setattr(
        svc,
        "settings",
        SimpleNamespace(sales_offer_download_api="https://x.example/api"),
    )
    monkeypatch.setattr(
        svc,
        "CurlAsyncSession",
        fake_session(base64.b64encode(b"not a pdf"), "text/plain"),
    )

    with pytest.raises(ValueError, match="not a PDF"):
        await svc.fetch_sales_offer_pdf(
            document_id="doc-1", access_token="tok", user_id="u"
        )
