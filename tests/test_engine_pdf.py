from __future__ import annotations

import pikepdf

from metascrub.config import CleanConfig
from metascrub.engines.pdf import PdfEngine


def test_probe_lists_docinfo_and_xmp(dirty_pdf):
    rows = PdfEngine().probe(str(dirty_pdf))
    fields = {r.field for r in rows}
    assert "Author" in fields
    assert "Producer" in fields
    assert any(r.namespace == "XMP" for r in rows)


def test_strip_removes_all_metadata(dirty_pdf, tmp_path):
    dst = tmp_path / "clean.pdf"
    result = PdfEngine().strip(str(dirty_pdf), str(dst), CleanConfig())

    assert result.status == "cleaned"
    assert result.removed
    assert dst.exists()

    with pikepdf.open(str(dst)) as pdf:
        assert "/Info" not in pdf.trailer
        assert "/Metadata" not in pdf.Root
    assert PdfEngine().probe(str(dst)) == []


def test_keep_fields_preserves_title(dirty_pdf, tmp_path):
    dst = tmp_path / "clean.pdf"
    cfg = CleanConfig(keep_fields=["Title"])
    result = PdfEngine().strip(str(dirty_pdf), str(dst), cfg)

    assert "Title" in result.kept
    with pikepdf.open(str(dst)) as pdf:
        assert str(pdf.docinfo.get("/Title")) == "Q3 Internal Forecast"
        assert "/Author" not in pdf.docinfo


def test_signed_pdf_is_skipped_not_broken(signed_pdf, tmp_path):
    dst = tmp_path / "out.pdf"
    result = PdfEngine().strip(str(signed_pdf), str(dst), CleanConfig())

    assert result.status == "skipped"
    assert "sign" in (result.reason or "").lower()
    assert not dst.exists()
    # original untouched
    with pikepdf.open(str(signed_pdf)) as pdf:
        assert str(pdf.docinfo.get("/Author")) == "Alice Example"


def test_strip_does_not_modify_source(dirty_pdf, tmp_path):
    before = dirty_pdf.read_bytes()
    PdfEngine().strip(str(dirty_pdf), str(tmp_path / "c.pdf"), CleanConfig())
    assert dirty_pdf.read_bytes() == before
