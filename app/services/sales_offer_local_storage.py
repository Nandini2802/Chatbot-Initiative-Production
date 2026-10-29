import asyncio
import os
import re
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STORAGE_ROOT = Path(
    os.getenv(
        "SALES_OFFER_STORAGE_DIR",
        str(PROJECT_ROOT / "storage" / "sales_offers"),
    )
).resolve()

MAX_PDF_BYTES = 10 * 1024 * 1024


def safe_pdf_filename(value: str) -> str:
    name = str(value or "SalesOffer.pdf")
    name = name.replace("\\", "/").split("/")[-1]

    name = re.sub(
        r"[^a-zA-Z0-9_.() -]",
        "_",
        name,
    ).strip(" .")

    if not name.lower().endswith(".pdf"):
        name += ".pdf"

    return name[:180]


def readable_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def _save_pdf(
    reference_id: uuid.UUID,
    pdf_bytes: bytes,
) -> str:

    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF content")

    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds 10 MB")

    STORAGE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path = STORAGE_ROOT / f"{reference_id}.pdf"

    # Exclusive creation prevents overwriting existing PDFs.
    with file_path.open("xb") as file:
        file.write(pdf_bytes)

    return str(file_path)


async def save_pdf_locally(
    reference_id: uuid.UUID,
    pdf_bytes: bytes,
) -> str:

    return await asyncio.to_thread(
        _save_pdf,
        reference_id,
        pdf_bytes,
    )