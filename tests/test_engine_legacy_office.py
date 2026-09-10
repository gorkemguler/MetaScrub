from __future__ import annotations

import zipfile

import olefile

from metascrub.config import CleanConfig
from metascrub.engines import engine_for
from metascrub.engines.legacy_office import LegacyOfficeEngine
from metascrub.engines.office import OfficeEngine


def test_dispatch_routes_legacy_extensions():
    for ext in ("doc", "xls", "ppt"):
        assert isinstance(engine_for(ext), LegacyOfficeEngine)


def test_probe_decodes_summary_information(legacy_doc):
    rows = {r.field: r.before for r in LegacyOfficeEngine().probe(str(legacy_doc))}
    assert rows.get("author") == "Bob Author"
    assert rows.get("last_saved_by") == "Carol Reviewer"
    assert not any(v.startswith("b'") for v in rows.values())     # decoded, not bytes repr
    assert not any("1601" in v for v in rows.values())            # OLE null dates filtered


def test_strip_in_place_via_pure_python_keeps_format(legacy_doc, tmp_path):
    dst = tmp_path / "out" / "memo.doc"
    result = LegacyOfficeEngine().strip(str(legacy_doc), str(dst), CleanConfig())

    assert result.status == "cleaned"
    assert result.out_path.endswith(".doc")            # format preserved — no LibreOffice
    assert result.removed
    assert dst.is_file() and dst.stat().st_size == legacy_doc.stat().st_size  # same size

    with olefile.OleFileIO(str(dst)) as ole:
        meta = ole.get_metadata()
        assert not (meta.author or b"").strip()
        assert not (meta.title or b"").strip()
    assert LegacyOfficeEngine().probe(str(dst)) == []


def test_in_place_now_supported_for_legacy(legacy_doc):
    report_engine = LegacyOfficeEngine()
    result = report_engine.strip(str(legacy_doc), str(legacy_doc) + ".tmp", CleanConfig(in_place=True))
    assert result.status == "cleaned"


def test_libreoffice_fallback_when_ole_patch_fails(monkeypatch, legacy_doc, tmp_path):
    import metascrub.engines.legacy_office as mod

    def boom(*_a, **_k):
        raise ValueError("simulated bad container")

    monkeypatch.setattr(mod, "scrub_ole2", boom)
    dst = tmp_path / "out" / "memo.doc"
    result = LegacyOfficeEngine().strip(str(legacy_doc), str(dst), CleanConfig(output_dir=str(tmp_path / "out")))

    if result.status == "cleaned":                     # LibreOffice present
        assert result.out_path.endswith(".docx")
        assert "LibreOffice" in (result.reason or "")
        assert OfficeEngine().probe(result.out_path) == []
    else:                                              # no soffice on this box
        assert result.status in ("error", "unsupported")


def test_unsupported_when_patch_fails_and_no_soffice(monkeypatch, tmp_path):
    import metascrub.engines.legacy_office as mod

    monkeypatch.setattr(mod, "scrub_ole2", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad")))
    monkeypatch.setattr(mod, "soffice_path", lambda: None)
    f = tmp_path / "old.doc"
    f.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    result = LegacyOfficeEngine().strip(str(f), str(tmp_path / "o.doc"), CleanConfig())
    assert result.status == "unsupported"
