from __future__ import annotations

import zipfile

from metascrub.config import CleanConfig
from metascrub.engines import engine_for
from metascrub.engines.legacy_office import LegacyOfficeEngine
from metascrub.engines.office import OfficeEngine


def test_dispatch_routes_legacy_extensions():
    for ext in ("doc", "xls", "ppt"):
        assert isinstance(engine_for(ext), LegacyOfficeEngine)


def test_unsupported_when_soffice_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("metascrub.engines.legacy_office.soffice_path", lambda: None)
    f = tmp_path / "old.doc"
    f.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)  # OLE2 magic
    result = LegacyOfficeEngine().strip(str(f), str(tmp_path / "o.doc"), CleanConfig())
    assert result.status == "unsupported"
    assert "LibreOffice" in (result.reason or "")


def test_in_place_refused(monkeypatch, tmp_path):
    monkeypatch.setattr("metascrub.engines.legacy_office.soffice_path", lambda: "/usr/bin/soffice")
    f = tmp_path / "old.doc"
    f.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    result = LegacyOfficeEngine().strip(str(f), str(tmp_path / "o.doc"), CleanConfig(in_place=True))
    assert result.status == "skipped"
    assert "in place" in (result.reason or "")


def test_probe_decodes_summary_information(legacy_doc):
    rows = {r.field: r.before for r in LegacyOfficeEngine().probe(str(legacy_doc))}
    assert rows.get("author") == "Bob Author"
    assert rows.get("last_saved_by") == "Carol Reviewer"
    assert not any(v.startswith("b'") for v in rows.values())     # decoded, not bytes repr
    assert not any("1601" in v for v in rows.values())            # OLE null dates filtered


def test_strip_converts_to_ooxml_and_scrubs(legacy_doc, tmp_path):
    dst = tmp_path / "out" / "memo.doc"
    result = LegacyOfficeEngine().strip(str(legacy_doc), str(dst), CleanConfig(output_dir=str(tmp_path / "out")))

    assert result.status == "cleaned"
    assert result.out_path.endswith(".docx")            # format changed
    assert "LibreOffice" in (result.reason or "")

    names = set(zipfile.ZipFile(result.out_path).namelist())
    assert "docProps/core.xml" not in names             # scrubbed by OfficeEngine
    assert OfficeEngine().probe(result.out_path) == []
