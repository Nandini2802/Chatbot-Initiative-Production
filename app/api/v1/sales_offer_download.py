import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.persistence.models import SalesOfferDocument

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sales-offer/download/{reference_id}")
async def download_sales_offer(
    reference_id: uuid.UUID,
    request: Request,
):
    logger.info(
        "SALES_OFFER_DOWNLOAD_REQUEST | reference_id=%s",
        reference_id,
    )

    # Reuse the PostgreSQL engine initialized in main.py
    clients = request.app.state.clients

    session_factory = async_sessionmaker(
        bind=clients.postgres,
        expire_on_commit=False,
        autoflush=False,
    )

    # Retrieve document metadata from PostgreSQL
    async with session_factory() as db:
        result = await db.execute(
            select(SalesOfferDocument).where(
                SalesOfferDocument.id == reference_id
            )
        )

        document = result.scalar_one_or_none()

        if document is None:
            logger.warning(
                "SALES_OFFER_DOCUMENT_NOT_FOUND | reference_id=%s",
                reference_id,
            )
            raise HTTPException(
                status_code=404,
                detail="Sales Offer document not found",
            )

        file_path_value = document.file_path
        file_name = document.file_name

    # Check whether the PDF exists locally
    file_path = Path(file_path_value)

    logger.info(
        "SALES_OFFER_FILE_CHECK | path=%s | exists=%s",
        file_path,
        file_path.is_file(),
    )

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="PDF file not found on server",
        )

    logger.info(
        "SALES_OFFER_DOWNLOAD_SUCCESS | file=%s",
        file_name,
    )

    # Return PDF directly to browser
    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type="application/pdf",
        content_disposition_type="attachment",
    )