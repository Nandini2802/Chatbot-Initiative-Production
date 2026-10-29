
import base64
import binascii
import json
import logging
import os
import re
import secrets
import uuid
from urllib.parse import quote, urlparse

from curl_cffi.requests import AsyncSession

from pathlib import Path

from curl_cffi.requests import AsyncSession as CurlAsyncSession
from sqlalchemy.ext.asyncio import AsyncSession as DBAsyncSession

from app.persistence.repositories.sales_offer_document_repo import (
    create_sales_offer_document,
)

from app.services.sales_offer_local_storage import (
    save_pdf_locally,
    safe_pdf_filename,
    readable_size,
)

logger = logging.getLogger(__name__)

DOWNLOAD_API = (
    "https://middleware-uat.danubeproperties.com"
    "/api/downloadGenericDoc"
)

DOWNLOAD_TTL_SECONDS = 600
MAX_PDF_BYTES = 10 * 1024 * 1024


def safe_pdf_filename(value: str) -> str:
    name = str(value or "SalesOffer.pdf")
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^a-zA-Z0-9_.() -]", "_", name)
    name = name.strip(" .")[:180] or "SalesOffer"

    if not name.lower().endswith(".pdf"):
        name += ".pdf"

    return name


def readable_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def get_public_base_url() -> str:
    base_url = os.getenv(
        "CHATBOT_PUBLIC_BASE_URL", ""
    ).strip().rstrip("/")

    if not base_url:
        raise RuntimeError(
            "CHATBOT_PUBLIC_BASE_URL is missing"
        )

    parsed = urlparse(base_url)

    is_local = (
        parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
    )

    if parsed.scheme != "https" and not is_local:
        raise RuntimeError(
            "CHATBOT_PUBLIC_BASE_URL must use HTTPS "
            "except for localhost testing"
        )

    if not parsed.netloc or parsed.username or parsed.password:
        raise RuntimeError("Invalid public base URL")

    return base_url


async def fetch_sales_offer_pdf(
    *,
    document_id: str,
    access_token: str,
    user_id: str,
) -> bytes:
    if not document_id or not access_token or not user_id:
        raise ValueError(
            "Missing document ID, Salesforce token, or user ID"
        )

    logger.info(
        "FLOW3_MIDDLEWARE_REQUEST | document_id=%s",
        document_id,
    )

    async with CurlAsyncSession(timeout=45) as session:
        response = await session.post(
            DOWNLOAD_API,
            headers={
                "salesforce_access_token": access_token,
                "user_id": str(user_id),
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain",
            },
            json={
                "salesOfferDocId": str(document_id)
            },
        )

        logger.info(
            "FLOW3_MIDDLEWARE_RESPONSE | status=%s | "
            "content_type=%s | body_length=%s",
            response.status_code,
            response.headers.get("Content-Type"),
            len(response.content),
        )

        logger.info(
            "SALES_OFFER_API_RESPONSE | status=%s | content_type=%s | content_length=%s",
            response.status_code,
            response.headers.get("Content-Type"),
            len(response.content),
        )

        response.raise_for_status()

        # Some middleware responses contain raw PDF bytes,
        # rather than a Base64-encoded string.
        if response.content.startswith(b"%PDF-"):
            pdf_bytes = response.content

            if len(pdf_bytes) > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds the 10 MB limit")

            logger.info(
                "FLOW3_PDF_RECEIVED_DIRECTLY | bytes=%s",
                len(pdf_bytes),
            )

            return pdf_bytes

        logger.info(
            "SALES_OFFER_PDF_RETRIEVED | size=%s | valid_pdf=%s",
            len(pdf_bytes),
            pdf_bytes.startswith(b"%PDF-"),
        )

        raw = response.text.strip()

        logger.warning(
            "FLOW3_RESPONSE_DEBUG | "
            "status=%s | "
            "content_type=%s | "
            "content_length=%s | "
            "starts_with_pdf=%s | "
            "first_16_bytes_hex=%s",
            response.status_code,
            response.headers.get("Content-Type"),
            len(response.content),
            response.content.startswith(b"%PDF-"),
            response.content[:16].hex(),
        )

        try:
            parsed = response.json()
        except ValueError:
            parsed = None

    if isinstance(parsed, str):
        encoded = parsed

    elif isinstance(parsed, dict):
        encoded = None

        for key in (
            "base64",
            "fileContent",
            "content",
            "pdfBase64",
            "data",
        ):
            value = parsed.get(key)

            if isinstance(value, str):
                encoded = value
                break

        if encoded is None:
            raise ValueError(
                "Middleware returned JSON without "
                "a supported Base64 PDF field"
            )

    else:
        encoded = raw

    encoded = encoded.strip()

    if encoded.startswith("data:application/pdf;base64,"):
        encoded = encoded.split(",", 1)[1]

    encoded = "".join(encoded.split())

    try:
        encoded.encode("ascii")
    except UnicodeEncodeError as exc:
        logger.error(
            "FLOW3_UNEXPECTED_RESPONSE | "
            "content_type=%s | "
            "first_16_bytes_hex=%s",
            response.headers.get("Content-Type"),
            response.content[:16].hex(),
        )

        raise ValueError(
            "Middleware response is neither a raw PDF "
            "nor an ASCII Base64 PDF. Check its response format."
        ) from exc

    if len(encoded) > MAX_PDF_BYTES * 4 // 3 + 100:
        raise ValueError("PDF exceeds the 10 MB limit")

    try:
        pdf_bytes = base64.b64decode(
            encoded,
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            "Middleware returned invalid Base64 PDF"
        ) from exc

    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError(
            "Decoded response is not a PDF"
        )

    if b"%%EOF" not in pdf_bytes[-2048:]:
        raise ValueError(
            "PDF is missing its EOF marker"
        )

    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 10 MB limit")

    logger.info(
        "FLOW3_PDF_DECODED | bytes=%s",
        len(pdf_bytes),
    )

    return pdf_bytes


async def create_sales_offer_download(
    *,
    db_session: DBAsyncSession,
    document_id: str,
    file_name: str,
    access_token: str,
    user_id: str,
    session_id: str,
) -> dict:

    # 1. Retrieve PDF from existing middleware.
    pdf_bytes = await fetch_sales_offer_pdf(
        document_id=document_id,
        access_token=access_token,
        user_id=user_id,
    )

    # 2. Generate permanent reference.
    reference_id = uuid.uuid4()
    print("reference_id", reference_id)

    # 3. Save PDF to local storage.
    file_path = await save_pdf_locally(
        reference_id=reference_id,
        pdf_bytes=pdf_bytes,
    )

    safe_name = safe_pdf_filename(file_name)

    try:
        # 4. Save metadata in PostgreSQL.
        await create_sales_offer_document(
            db_session,
            reference_id=reference_id,
            user_id=user_id,
            session_id=session_id,
            sales_offer_doc_id=document_id,
            file_name=safe_name,
            file_path=file_path,
        )

        # 5. Commit before publishing download URL.
        await db_session.commit()

        logger.info(
            "SALES_OFFER_DB_SAVED | reference_id=%s | document_id=%s",
            reference_id,
            document_id,
        )

    except Exception:
        await db_session.rollback()

        # Avoid leaving orphan files when DB saving fails.
        Path(file_path).unlink(missing_ok=True)
        raise

    # 6. Return permanent download reference.
    download_path = (
        f"/api/v1/sales-offer/download/{reference_id}"
    )

    public_base_url = os.getenv(
        "CHATBOT_PUBLIC_BASE_URL",
        "",
    ).rstrip("/")

    download_url = (
        f"{public_base_url}{download_path}"
        if public_base_url
        else download_path
    )

    return {
        "reference_id": str(reference_id),
        "file_name": safe_name,
        "file_size": readable_size(len(pdf_bytes)),
        "download_url": download_url,
    }