from __future__ import annotations

import os

import pikepdf

from metascrub.cleaner import clean_paths
from metascrub.config import CleanConfig


def test_clean_tree_mirrors_structure_and_leaves_originals(dirty_tree):
    out = dirty_tree.parent / "out"
    cfg = CleanConfig(output_dir=str(out))
    report = clean_paths([str(dirty_tree)], cfg, base_dir=str(dirty_tree))

    assert {r.status for r in report.results} == {"cleaned"}
    assert (out / "forecast.pdf").exists()
    assert (out / "sub" / "memo2.docx").exists()          # subdir preserved
    assert not report.files_with_residual

    # originals untouched
    with pikepdf.open(str(dirty_tree / "forecast.pdf")) as pdf:
        assert "/Info" in pdf.trailer


def test_dry_run_writes_nothing(dirty_tree):
    out = dirty_tree.parent / "out2"
    report = clean_paths([str(dirty_tree)], CleanConfig(output_dir=str(out), dry_run=True),
                         base_dir=str(dirty_tree))
    assert not out.exists()
    assert all(r.status == "skipped" and r.reason == "dry-run" for r in report.results)
    assert report.fields_removed > 0  # "would remove" rows still populated


def test_in_place_overwrites_original(dirty_pdf):
    report = clean_paths([str(dirty_pdf)], CleanConfig(in_place=True))
    r = report.results[0]
    assert r.status == "cleaned"
    assert r.out_path == str(dirty_pdf)
    with pikepdf.open(str(dirty_pdf)) as pdf:
        assert "/Info" not in pdf.trailer
    assert not any(p.endswith(".metascrub-tmp") for p in os.listdir(dirty_pdf.parent))


def test_unsupported_extension_reported(tmp_path):
    f = tmp_path / "note.rtf"
    f.write_text("hello")
    report = clean_paths([str(f)], CleanConfig(filetypes=["rtf"]))
    assert report.results[0].status == "unsupported"


def test_verify_populates_residual(monkeypatch, dirty_docx, tmp_path):
    # Force probe() to always "see" leftover metadata so the verify path is exercised.
    from metascrub import cleaner
    from metascrub.models import FieldChange

    real = cleaner.engine_for

    class Wrapped:
        def __init__(self, e):
            self._e = e
            self.name = e.name

        def probe(self, p):
            return [FieldChange("XMP", "leftover", "x")]

        def strip(self, s, d, c):
            return self._e.strip(s, d, c)

    monkeypatch.setattr(cleaner, "engine_for", lambda ext: Wrapped(real(ext)))
    report = clean_paths([str(dirty_docx)], CleanConfig(output_dir=str(tmp_path / "o")))
    assert report.results[0].residual == ["XMP:leftover"]
