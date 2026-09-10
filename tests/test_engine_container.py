from __future__ import annotations

import email.message
import email.policy
import io
import zipfile

import pikepdf

from metascrub.config import CleanConfig
from metascrub.engines import engine_for
from metascrub.engines.container import ContainerEngine


def _dirty_pdf_bytes(author="Zip Zara"):
    p = pikepdf.new()
    p.add_blank_page(page_size=(80, 80))
    p.docinfo["/Author"] = author
    buf = io.BytesIO()
    p.save(buf)
    return buf.getvalue()


def test_dispatch():
    assert isinstance(engine_for("zip"), ContainerEngine)
    assert isinstance(engine_for("eml"), ContainerEngine)


def test_zip_members_scrubbed_others_kept(tmp_path):
    src = tmp_path / "bundle.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("docs/inner.pdf", _dirty_pdf_bytes())
        z.writestr("notes.txt", b"plain text, untouched")

    assert any("inner.pdf" in r.namespace for r in ContainerEngine().probe(str(src)))

    dst = tmp_path / "clean.zip"
    result = ContainerEngine().strip(str(src), str(dst), CleanConfig(recurse=True))
    assert result.status == "cleaned" and result.removed

    with zipfile.ZipFile(dst) as z:
        assert z.read("notes.txt") == b"plain text, untouched"
        with pikepdf.open(io.BytesIO(z.read("docs/inner.pdf"))) as p:
            assert "/Info" not in p.trailer
    assert ContainerEngine().probe(str(dst)) == []


def test_eml_attachment_scrubbed(tmp_path):
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"] = "a@b.c", "d@e.f", "hi"
    m.set_content("see attached")
    m.add_attachment(_dirty_pdf_bytes("Mail Mary"), maintype="application",
                     subtype="pdf", filename="report.pdf")
    src = tmp_path / "mail.eml"
    src.write_bytes(m.as_bytes())

    dst = tmp_path / "clean.eml"
    result = ContainerEngine().strip(str(src), str(dst), CleanConfig(recurse=True))
    assert result.status == "cleaned"

    out = email.message_from_bytes(dst.read_bytes(), policy=email.policy.default)
    atts = [p for p in out.walk() if p.get_content_disposition() == "attachment"]
    assert atts
    with pikepdf.open(io.BytesIO(atts[0].get_payload(decode=True))) as p:
        assert "/Info" not in p.trailer


def test_depth_limit(tmp_path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("x.pdf", _dirty_pdf_bytes())
    src = tmp_path / "outer.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("nested.zip", inner.getvalue())

    # a deep _recurse_depth means the nested zip is skipped, not descended
    cfg = CleanConfig(recurse=True)
    object.__setattr__(cfg, "_recurse_depth", 9)
    result = ContainerEngine().strip(str(src), str(tmp_path / "o.zip"), cfg)
    assert result.status == "skipped" and "depth" in (result.reason or "")
