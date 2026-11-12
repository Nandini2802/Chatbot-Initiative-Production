"""Sales offer PDF names keep the whole API name; slashes become '-'."""
import pytest

from app.services.sales_offer_download_service import safe_pdf_filename as dl
from app.services.sales_offer_local_storage import safe_pdf_filename as local


@pytest.mark.parametrize("fn", [dl, local])
@pytest.mark.parametrize("raw,expected", [
    ("GRZ/101/2026", "GRZ-101-2026.pdf"),
    ("SO/GRZ-101/2026.pdf", "SO-GRZ-101-2026.pdf"),
    ("SO\\GRZ\\101\\2026", "SO-GRZ-101-2026.pdf"),
    ("SO-GRZ-101-2026", "SO-GRZ-101-2026.pdf"),
    ("Sales Offer - GRZ 101", "Sales Offer - GRZ 101.pdf"),
    ("Offer A.pdf", "Offer A.pdf"),
    (None, "SalesOffer.pdf"),
    ("", "SalesOffer.pdf"),
])
def test_names(fn, raw, expected):
    assert fn(raw) == expected


@pytest.mark.parametrize("fn", [dl, local])
@pytest.mark.parametrize("raw", ["../../etc/passwd", "..\\..\\x", "/abs/path.pdf", "a/../b"])
def test_no_path_survives(fn, raw):
    out = fn(raw)
    assert "/" not in out and "\\" not in out
    assert not out.startswith(".")
    assert out.endswith(".pdf")
