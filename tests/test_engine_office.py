from __future__ import annotations

import zipfile

from metascrub.config import CleanConfig
from metascrub.engines.office import OfficeEngine


def _names(path) -> set[str]:
    with zipfile.ZipFile(path) as z:
        return set(z.namelist())


def test_probe_lists_core_app_custom(dirty_docx):
    rows = OfficeEngine().probe(str(dirty_docx))
    fields = {r.field for r in rows}
    assert {"creator", "lastModifiedBy", "Company", "Manager", "Matter Number"} <= fields
    assert any(r.field == "w:rsids" for r in rows)


def test_strip_removes_metadata_parts(dirty_docx, tmp_path):
    dst = tmp_path / "clean.docx"
    result = OfficeEngine().strip(str(dirty_docx), str(dst), CleanConfig())

    assert result.status == "cleaned"
    names = _names(dst)
    assert "docProps/core.xml" not in names
    assert "docProps/app.xml" not in names
    assert "docProps/custom.xml" not in names
    assert "word/document.xml" in names  # content untouched
    assert OfficeEngine().probe(str(dst)) == []


def test_strip_prunes_dangling_relationships(dirty_docx, tmp_path):
    dst = tmp_path / "clean.docx"
    OfficeEngine().strip(str(dirty_docx), str(dst), CleanConfig())
    with zipfile.ZipFile(dst) as z:
        rels = z.read("_rels/.rels").decode()
        ctypes = z.read("[Content_Types].xml").decode()
    assert "core.xml" not in rels and "custom.xml" not in rels
    assert "core.xml" not in ctypes and "app.xml" not in ctypes


def test_strip_normalises_member_timestamps(dirty_docx, tmp_path):
    dst = tmp_path / "clean.docx"
    OfficeEngine().strip(str(dirty_docx), str(dst), CleanConfig())
    with zipfile.ZipFile(dst) as z:
        assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in z.infolist())


def test_keep_title_regenerates_minimal_core(dirty_docx, tmp_path):
    dst = tmp_path / "clean.docx"
    result = OfficeEngine().strip(str(dirty_docx), str(dst), CleanConfig(keep_fields=["title"]))
    assert "title" in result.kept
    with zipfile.ZipFile(dst) as z:
        core = z.read("docProps/core.xml").decode()
    assert "Confidential Merger Memo" in core
    assert "Bob Author" not in core


def test_rsids_stripped_from_settings(dirty_docx, tmp_path):
    dst = tmp_path / "clean.docx"
    OfficeEngine().strip(str(dirty_docx), str(dst), CleanConfig())
    with zipfile.ZipFile(dst) as z:
        settings = z.read("word/settings.xml").decode()
    assert "rsid" not in settings and "proofState" not in settings


def test_odf_meta_emptied(dirty_odt, tmp_path):
    dst = tmp_path / "clean.odt"
    result = OfficeEngine().strip(str(dirty_odt), str(dst), CleanConfig())
    assert result.status == "cleaned"
    with zipfile.ZipFile(dst) as z:
        meta = z.read("meta.xml").decode()
        # mimetype must stay first + stored for a valid ODF package
        first = z.infolist()[0]
    assert "Erin Writer" not in meta and "LibreOffice" not in meta
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert OfficeEngine().probe(str(dst)) == []


def test_source_not_modified(dirty_docx, tmp_path):
    before = dirty_docx.read_bytes()
    OfficeEngine().strip(str(dirty_docx), str(tmp_path / "c.docx"), CleanConfig())
    assert dirty_docx.read_bytes() == before
