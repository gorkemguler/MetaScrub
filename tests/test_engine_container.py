from __future__ import annotations

import email.message
import email.policy
import io
import tarfile
import zipfile

import pikepdf
import pytest

from metacls.config import CleanConfig
from metacls.engines import engine_for
from metacls.engines.container import ContainerEngine

_HAS_PY7ZR = __import__("importlib").util.find_spec("py7zr") is not None
_HAS_EXTRACT_MSG = __import__("importlib").util.find_spec("extract_msg") is not None


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


def test_dispatch_new_container_kinds():
    for ext in ("tar", "tgz", "7z", "msg", "gz"):
        assert isinstance(engine_for(ext), ContainerEngine), ext


@pytest.mark.parametrize("suffix,mode", [(".tar", "w"), (".tar.gz", "w:gz"), (".tgz", "w:gz")])
def test_tar_members_scrubbed_and_headers_normalised(tmp_path, suffix, mode):
    src = tmp_path / f"bundle{suffix}"
    with tarfile.open(src, mode) as t:
        info = tarfile.TarInfo("docs/inner.pdf")
        payload = _dirty_pdf_bytes("Tar Tara")
        info.size = len(payload)
        info.uid, info.gid, info.uname, info.gname = 501, 20, "gorkem", "staff"
        info.mtime = 1_700_000_000
        t.addfile(info, io.BytesIO(payload))
        note = tarfile.TarInfo("notes.txt")
        note.size = 5
        t.addfile(note, io.BytesIO(b"plain"))

    assert any("inner.pdf" in r.namespace for r in ContainerEngine().probe(str(src)))

    dst = tmp_path / f"clean{suffix}"
    result = ContainerEngine().strip(str(src), str(dst), CleanConfig(recurse=True))
    assert result.status == "cleaned"

    with tarfile.open(dst, "r:*") as t:
        pdf_m = t.getmember("docs/inner.pdf")
        assert (pdf_m.uid, pdf_m.gid, pdf_m.uname, pdf_m.gname, pdf_m.mtime) == (0, 0, "", "", 0)
        with pikepdf.open(io.BytesIO(t.extractfile("docs/inner.pdf").read())) as p:
            assert "/Info" not in p.trailer
        assert t.extractfile("notes.txt").read() == b"plain"
    assert ContainerEngine().probe(str(dst)) == []


def test_bare_gz_that_is_not_a_tar_is_unsupported(tmp_path):
    import gzip

    f = tmp_path / "notes.txt.gz"
    f.write_bytes(gzip.compress(b"just a gzipped text file"))
    result = ContainerEngine().strip(str(f), str(tmp_path / "o"), CleanConfig(recurse=True))
    assert result.status == "unsupported"


@pytest.mark.skipif(not _HAS_PY7ZR, reason="py7zr not installed")
def test_7z_members_scrubbed(tmp_path):
    import py7zr

    src = tmp_path / "bundle.7z"
    with py7zr.SevenZipFile(src, "w") as z:
        z.writef(io.BytesIO(_dirty_pdf_bytes("Seven Sam")), "inner.pdf")
        z.writef(io.BytesIO(b"plain text"), "notes.txt")

    assert any("inner.pdf" in r.namespace for r in ContainerEngine().probe(str(src)))

    dst = tmp_path / "clean.7z"
    result = ContainerEngine().strip(str(src), str(dst), CleanConfig(recurse=True))
    assert result.status == "cleaned" and result.removed

    out = tmp_path / "unpacked"
    with py7zr.SevenZipFile(dst, "r") as z:
        z.extractall(path=out)
    assert (out / "notes.txt").read_bytes() == b"plain text"
    with pikepdf.open(str(out / "inner.pdf")) as p:
        assert "/Info" not in p.trailer
    assert ContainerEngine().probe(str(dst)) == []


def test_7z_without_py7zr_is_skipped(tmp_path, monkeypatch):
    from metacls.engines import container as cmod

    monkeypatch.setattr(cmod, "_have_py7zr", lambda: False)
    f = tmp_path / "x.7z"
    f.write_bytes(b"7z\xbc\xaf\x27\x1c...")
    result = ContainerEngine().strip(str(f), str(tmp_path / "o.7z"), CleanConfig(recurse=True))
    assert result.status == "skipped" and "py7zr" in (result.reason or "")


@pytest.mark.skipif(not _HAS_EXTRACT_MSG, reason="extract-msg not installed")
def test_msg_is_probe_only(tmp_path):
    # A real .msg is a CFB; building one is heavy, so just prove the
    # engine routes .msg to a read-only 'skipped' strip.
    f = tmp_path / "mail.msg"
    f.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512)  # CFB magic
    result = ContainerEngine().strip(str(f), str(tmp_path / "o.msg"), CleanConfig(recurse=True))
    assert result.status == "skipped" and ".msg" in (result.reason or "")


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
