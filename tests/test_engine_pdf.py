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


# --- v0.2: annotations, attachments, encryption, /ID -----------------------


def test_annotation_author_and_dates_removed_content_kept(annotated_pdf, tmp_path):
    probed = {r.field for r in PdfEngine().probe(str(annotated_pdf))}
    assert "Page 1 T" in probed and "Page 1 M" in probed and "Page 1 CreationDate" in probed

    dst = tmp_path / "clean.pdf"
    result = PdfEngine().strip(str(annotated_pdf), str(dst), CleanConfig())
    assert result.status == "cleaned"
    assert PdfEngine().probe(str(dst)) == []

    with pikepdf.open(str(dst)) as pdf:
        annot = pdf.pages[0].Annots[0]
        assert "/T" not in annot and "/M" not in annot and "/CreationDate" not in annot
        assert str(annot.Contents) == "Please revise this section"   # content untouched


def test_widget_field_name_is_preserved(annotated_pdf, tmp_path):
    dst = tmp_path / "clean.pdf"
    PdfEngine().strip(str(annotated_pdf), str(dst), CleanConfig())
    with pikepdf.open(str(dst)) as pdf:
        widget = pdf.pages[0].Annots[1]
        assert str(widget.Subtype) == "/Widget"
        assert str(widget.T) == "signature_field"   # form field name, not an author


def test_embedded_file_metadata_stripped_but_file_kept(attachment_pdf, tmp_path):
    probed = {r.field for r in PdfEngine().probe(str(attachment_pdf))}
    assert "q3.xlsx Desc" in probed and "q3.xlsx ModDate" in probed

    dst = tmp_path / "clean.pdf"
    PdfEngine().strip(str(attachment_pdf), str(dst), CleanConfig())
    assert PdfEngine().probe(str(dst)) == []

    with pikepdf.open(str(dst)) as pdf:
        spec = pdf.Root.Names.EmbeddedFiles.Names[1]
        assert "/Desc" not in spec
        params = spec.EF.F.Params
        assert "/CreationDate" not in params and "/ModDate" not in params
        assert bytes(spec.EF.F.read_bytes()) == b"quarterly numbers, do not share"  # file kept


def test_encrypted_pdf_skipped_without_password(encrypted_pdf, tmp_path):
    dst = tmp_path / "out.pdf"
    result = PdfEngine().strip(str(encrypted_pdf), str(dst), CleanConfig())
    assert result.status == "skipped"
    assert "encrypted" in (result.reason or "")
    assert not dst.exists()


def test_encrypted_pdf_wrong_password_is_error(encrypted_pdf, tmp_path):
    result = PdfEngine().strip(str(encrypted_pdf), str(tmp_path / "o.pdf"),
                               CleanConfig(pdf_password="nope"))
    assert result.status == "error"
    assert "password" in (result.error or "").lower()


def test_encrypted_pdf_scrubbed_with_password(encrypted_pdf, tmp_path):
    dst = tmp_path / "clean.pdf"
    result = PdfEngine().strip(str(encrypted_pdf), str(dst), CleanConfig(pdf_password="s3cret"))
    assert result.status == "cleaned"
    assert "encrypted" in (result.reason or "")
    with pikepdf.open(str(dst)) as pdf:            # opens with no password
        assert not pdf.is_encrypted
        assert "/Info" not in pdf.trailer
    assert PdfEngine().probe(str(dst)) == []


def test_probe_encrypted_without_password_reports_encryption(encrypted_pdf):
    rows = PdfEngine().probe(str(encrypted_pdf))
    assert len(rows) == 1 and rows[0].field == "encryption"


def test_strip_pdf_id_randomises_between_runs(dirty_pdf, tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    PdfEngine().strip(str(dirty_pdf), str(a), CleanConfig(strip_pdf_id=True))
    PdfEngine().strip(str(dirty_pdf), str(b), CleanConfig(strip_pdf_id=True))
    with pikepdf.open(str(a)) as pa, pikepdf.open(str(b)) as pb:
        assert bytes(pa.trailer.ID[0]) != bytes(pb.trailer.ID[0])

    c, d = tmp_path / "c.pdf", tmp_path / "d.pdf"
    PdfEngine().strip(str(dirty_pdf), str(c), CleanConfig())   # deterministic default
    PdfEngine().strip(str(dirty_pdf), str(d), CleanConfig())
    with pikepdf.open(str(c)) as pc, pikepdf.open(str(d)) as pd_:
        assert bytes(pc.trailer.ID[0]) == bytes(pd_.trailer.ID[0])
