import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import SalesOfferDocument


async def create_sales_offer_document(
    db: AsyncSession,
    *,
    reference_id: uuid.UUID,
    user_id: str,
    session_id: str,
    sales_offer_doc_id: str,
    file_name: str,
    file_path: str,
):
    document = SalesOfferDocument(
        id=reference_id,
        user_id=str(user_id),
        session_id=str(session_id),
        sales_offer_doc_id=str(sales_offer_doc_id),
        file_name=file_name,
        file_path=file_path,
    )

    db.add(document)
    await db.flush()

    return document


async def find_sales_offer_document(
    db: AsyncSession,
    *,
    reference_id: uuid.UUID,
    user_id: str,
):
    statement = select(SalesOfferDocument).where(
        SalesOfferDocument.id == reference_id,
        SalesOfferDocument.user_id == str(user_id),
    )

    result = await db.execute(statement)

    return result.scalar_one_or_none()