from __future__ import annotations

import os

import pikepdf

from metacls.cleaner import clean_paths
from metacls.config import CleanConfig


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
    assert not any(p.endswith(".metacls-tmp") for p in os.listdir(dirty_pdf.parent))


def test_backup_keeps_original_next_to_in_place_scrub(dirty_pdf):
    original = dirty_pdf.read_bytes()
    clean_paths([str(dirty_pdf)], CleanConfig(in_place=True, backup=True))

    backup = dirty_pdf.with_name(dirty_pdf.name + ".orig")
    assert backup.exists() and backup.read_bytes() == original
    with pikepdf.open(str(dirty_pdf)) as pdf:            # the file itself was scrubbed
        assert "/Info" not in pdf.trailer


def test_quarantine_moves_original_and_scrubs_in_place(dirty_tree, tmp_path):
    q = tmp_path / "quarantine"
    report = clean_paths([str(dirty_tree)], CleanConfig(quarantine=str(q)), base_dir=str(dirty_tree))
    assert {r.status for r in report.results} == {"cleaned"}

    # originals overwritten in place...
    with pikepdf.open(str(dirty_tree / "forecast.pdf")) as pdf:
        assert "/Info" not in pdf.trailer
    # ...but recoverable from quarantine/<date>/<relpath>
    import datetime
    day = datetime.date.today().isoformat()
    assert (q / day / "forecast.pdf").is_file()
    assert (q / day / "sub" / "memo2.docx").is_file()
    with pikepdf.open(str(q / day / "forecast.pdf")) as pdf:
        assert "/Info" in pdf.trailer      # the quarantined copy still has metadata


def test_on_result_called_once_per_file(dirty_tree, tmp_path):
    seen = []
    report = clean_paths([str(dirty_tree)], CleanConfig(output_dir=str(tmp_path / "o")),
                         base_dir=str(dirty_tree), on_result=seen.append)
    assert len(seen) == len(report.results)
    assert {r.src_path for r in seen} == {r.src_path for r in report.results}


def test_exclude_and_follow_symlinks_flow_through_config(dirty_tree, tmp_path):
    report = clean_paths([str(dirty_tree)],
                         CleanConfig(output_dir=str(tmp_path / "o"), exclude=["*.jpg"]),
                         base_dir=str(dirty_tree))
    assert not any(r.src_path.endswith(".jpg") for r in report.results)


def test_tool_versions_reports_the_optional_libraries():
    from metacls.engines import tool_versions

    v = tool_versions()
    assert v["metacls"] and "pikepdf" in v
    # olefile is a core dep; mutagen/pillow are extras that are installed in dev
    assert "olefile" in v


def test_jobs_parallel_matches_sequential(dirty_tree, tmp_path):
    seq = clean_paths([str(dirty_tree)], CleanConfig(output_dir=str(tmp_path / "a")),
                      base_dir=str(dirty_tree))
    par = clean_paths([str(dirty_tree)], CleanConfig(output_dir=str(tmp_path / "b"), jobs=4),
                      base_dir=str(dirty_tree))
    assert sorted(r.src_path for r in seq.results) == sorted(r.src_path for r in par.results)
    assert seq.fields_removed == par.fields_removed
    assert {r.status for r in par.results} == {"cleaned"}


def test_backup_does_not_clobber_existing_orig(dirty_pdf):
    backup = dirty_pdf.with_name(dirty_pdf.name + ".orig")
    backup.write_bytes(b"an earlier original")
    clean_paths([str(dirty_pdf)], CleanConfig(in_place=True, backup=True))
    assert backup.read_bytes() == b"an earlier original"


def test_unsupported_extension_reported(tmp_path):
    f = tmp_path / "note.rtf"
    f.write_text("hello")
    report = clean_paths([str(f)], CleanConfig(filetypes=["rtf"]))
    assert report.results[0].status == "unsupported"


def test_verify_populates_residual(monkeypatch, dirty_docx, tmp_path):
    # Force probe() to always "see" leftover metadata so the verify path is exercised.
    from metacls import cleaner
    from metacls.models import FieldChange

    real = cleaner.engine_for

    class Wrapped:
        def __init__(self, e):
            self._e = e
            self.name = e.name

        def probe(self, p, cfg=None):
            return [FieldChange("XMP", "leftover", "x")]

        def strip(self, s, d, c):
            return self._e.strip(s, d, c)

    monkeypatch.setattr(cleaner, "engine_for", lambda ext: Wrapped(real(ext)))
    report = clean_paths([str(dirty_docx)], CleanConfig(output_dir=str(tmp_path / "o")))
    assert report.results[0].residual == ["XMP:leftover"]
