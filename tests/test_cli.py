from __future__ import annotations

import json

from click.testing import CliRunner

from metascrub.cli import main


def test_inspect_shows_metadata(dirty_pdf):
    result = CliRunner().invoke(main, ["inspect", str(dirty_pdf), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    fields = {row["field"] for rows in data.values() for row in rows}
    assert "Author" in fields


def test_clean_copies_and_reports(dirty_tree, tmp_path):
    out = tmp_path / "cleaned"
    result = CliRunner().invoke(
        main, ["clean", str(dirty_tree), "--out", str(out), "--report-lang", "tr"]
    )
    assert result.exit_code == 0, result.output
    assert (out / "forecast.pdf").exists()
    report = json.loads((out / "report.json").read_text())
    assert report["summary"]["by_status"]["cleaned"] == 4
    assert report["summary"]["fields_removed"] > 0
    assert (out / "report.html").exists()


def test_clean_dry_run_exit_zero_no_writes(dirty_pdf, tmp_path):
    out = tmp_path / "cleaned"
    result = CliRunner().invoke(
        main, ["clean", str(dirty_pdf), "--dry-run", "--out", str(out),
               "--no-json-report", "--no-html-report"]
    )
    assert result.exit_code == 0
    assert not out.exists()


def test_clean_in_place_needs_confirmation(dirty_pdf):
    result = CliRunner().invoke(main, ["clean", str(dirty_pdf), "--in-place"], input="n\n")
    assert result.exit_code == 1
    assert "overwrite" in result.output.lower()


def test_clean_exit_2_when_residual(monkeypatch, dirty_pdf, tmp_path):
    from metascrub import cleaner

    real = cleaner.engine_for
    monkeypatch.setattr(cleaner, "engine_for", lambda ext: _Leftover(real(ext)))

    result = CliRunner().invoke(
        main, ["clean", str(dirty_pdf), "--out", str(tmp_path / "o"),
               "--no-json-report", "--no-html-report"]
    )
    assert result.exit_code == 2


class _Leftover:
    def __init__(self, e):
        self._e = e
        self.name = e.name

    def probe(self, p, cfg=None):
        from metascrub.models import FieldChange

        return [FieldChange("XMP", "leftover", "x")]

    def strip(self, s, d, c):
        return self._e.strip(s, d, c)
