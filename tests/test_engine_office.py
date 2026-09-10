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
    before = {r.field for r in OfficeEngine().probe(str(dirty_odt))}
    assert {"initial-creator", "creator", "generator"} <= before   # probe actually reads <office:meta>

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


_ODF_MANIFEST = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">'
    '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
    '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
    '<manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>'
    '<manifest:file-entry manifest:full-path="Thumbnails/thumbnail.png" manifest:media-type="image/png"/>'
    '</manifest:manifest>'
)
_ODF_META = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"><office:meta>'
    "<meta:initial-creator>Olga Odt</meta:initial-creator></office:meta></office:document-meta>"
)


def _odt_with_thumbnail(path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/manifest.xml", _ODF_MANIFEST)
        z.writestr("meta.xml", _ODF_META)
        z.writestr("content.xml", '<?xml version="1.0"?><doc/>')
        z.writestr("Thumbnails/thumbnail.png", b"\x89PNG\r\n\x1a\n fake preview bytes")


def test_odf_thumbnail_dropped_and_manifest_pruned(tmp_path):
    src = tmp_path / "notes.odt"
    _odt_with_thumbnail(src)

    fields = {r.field for r in OfficeEngine().probe(str(src))}
    assert "thumbnail" in fields and "initial-creator" in fields

    dst = tmp_path / "clean.odt"
    result = OfficeEngine().strip(str(src), str(dst), CleanConfig())
    assert result.status == "cleaned"

    with zipfile.ZipFile(dst) as z:
        names = set(z.namelist())
        manifest = z.read("META-INF/manifest.xml").decode()
    assert not any(n.startswith("Thumbnails/") for n in names)
    assert "Thumbnails/thumbnail.png" not in manifest
    assert "content.xml" in manifest          # the other entries are left alone
    assert OfficeEngine().probe(str(dst)) == []


def _docm_with_vba(path) -> None:
    ct = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.ms-word.document.macroEnabled.main+xml"/></Types>')
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="r2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
    core = ('<?xml version="1.0"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Macro Mike</dc:creator></cp:coreProperties>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("word/document.xml", "<w:document/>")
        z.writestr("word/vbaProject.bin", b"\x00\x01\x02 fake OLE macro storage \x03\x04")


def test_macro_enabled_docm_scrubs_core_and_flags_vba(tmp_path):
    src = tmp_path / "report.docm"
    _docm_with_vba(src)

    assert {r.field for r in OfficeEngine().probe(str(src))} >= {"creator"}

    dst = tmp_path / "clean.docm"
    result = OfficeEngine().strip(str(src), str(dst), CleanConfig())
    assert result.status == "cleaned"
    # core.xml gone, macro storage kept (breaking macros is worse), and the
    # report says so rather than silently leaving it out.
    with zipfile.ZipFile(dst) as z:
        names = set(z.namelist())
    assert "docProps/core.xml" not in names
    assert "word/vbaProject.bin" in names
    assert "vbaProject.bin" in result.kept
    assert OfficeEngine().probe(str(dst)) == []


def test_tracked_change_authors_kept_by_default(tracked_docx, tmp_path):
    dst = tmp_path / "c.docx"
    OfficeEngine().strip(str(tracked_docx), str(dst), CleanConfig())
    with zipfile.ZipFile(dst) as z:
        assert b"Dave Editor" in z.read("word/document.xml")


def test_strip_office_authors_blanks_names_and_dates_keeps_markup(tracked_docx, tmp_path):
    cfg = CleanConfig(strip_office_authors=True)
    probed = {r.field: r.before for r in OfficeEngine().probe(str(tracked_docx), cfg)}
    assert "Dave Editor" in probed.get("document.xml", "")
    assert "Frank Legal" in probed.get("comments.xml", "")

    dst = tmp_path / "c.docx"
    result = OfficeEngine().strip(str(tracked_docx), str(dst), cfg)
    assert result.status == "cleaned"

    with zipfile.ZipFile(dst) as z:
        doc = z.read("word/document.xml").decode()
        com = z.read("word/comments.xml").decode()
        ppl = z.read("word/people.xml").decode()
    for name in ("Dave Editor", "Erin Reviewer", "Frank Legal", "S-1-5-21-frank"):
        assert name not in doc and name not in com and name not in ppl
    assert 'w:date="' not in doc and 'w:date="' not in com
    assert "<w:ins " in doc and "<w:del " in doc          # change markup preserved
    assert "<w:comment " in com                           # comment (minus author) preserved
    assert OfficeEngine().probe(str(dst), cfg) == []
