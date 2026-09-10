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


def test_policy_publish_enables_opt_ins(monkeypatch, dirty_pdf, tmp_path):
    seen = {}
    from metascrub import cli as climod

    real = climod.clean_paths

    def spy(roots, cfg, **kw):
        seen["cfg"] = cfg
        return real(roots, cfg, **kw)

    monkeypatch.setattr(climod, "clean_paths", spy)
    CliRunner().invoke(main, ["clean", str(dirty_pdf), "--policy", "publish",
                              "--out", str(tmp_path / "o"), "--no-json-report", "--no-html-report"])
    assert seen["cfg"].strip_pdf_id and seen["cfg"].strip_form_values and seen["cfg"].strip_office_authors


def test_policy_internal_keeps_title(monkeypatch, dirty_pdf, tmp_path):
    seen = {}
    from metascrub import cli as climod

    def spy(roots, cfg, **kw):
        seen["cfg"] = cfg
        from metascrub.cleaner import clean_paths as real
        return real(roots, cfg, **kw)

    monkeypatch.setattr(climod, "clean_paths", spy)
    CliRunner().invoke(main, ["clean", str(dirty_pdf), "--policy", "internal",
                              "--out", str(tmp_path / "o"), "--no-json-report", "--no-html-report"])
    assert "Title" in seen["cfg"].keep_fields


def test_project_config_toml_sets_defaults(dirty_pdf, tmp_path, monkeypatch):
    (tmp_path / ".metascrub.toml").write_text("[clean]\njobs = 7\nstrip-pdf-id = true\n")
    monkeypatch.chdir(tmp_path)
    seen = {}
    from metascrub import cli as climod

    def spy(roots, cfg, **kw):
        seen["cfg"] = cfg
        from metascrub.cleaner import clean_paths as real
        return real(roots, cfg, **kw)

    monkeypatch.setattr(climod, "clean_paths", spy)
    CliRunner().invoke(main, ["clean", str(dirty_pdf), "--out", str(tmp_path / "o"),
                              "--no-json-report", "--no-html-report"])
    assert seen["cfg"].jobs == 7 and seen["cfg"].strip_pdf_id is True


def test_check_exit_3_on_metadata_then_0_when_clean(dirty_pdf, tmp_path):
    r = CliRunner().invoke(main, ["clean", str(dirty_pdf), "--check",
                                  "--no-json-report", "--no-html-report"])
    assert r.exit_code == 3
    assert "carry metadata" in r.output

    out = tmp_path / "c"
    CliRunner().invoke(main, ["clean", str(dirty_pdf), "--out", str(out),
                              "--no-json-report", "--no-html-report"])
    r2 = CliRunner().invoke(main, ["clean", str(out / dirty_pdf.name), "--check",
                                   "--no-json-report", "--no-html-report"])
    assert r2.exit_code == 0 and "No metadata found" in r2.output


def test_clean_exclude_glob_skips_matches(dirty_tree, tmp_path):
    out = tmp_path / "cleaned"
    result = CliRunner().invoke(
        main, ["clean", str(dirty_tree), "--out", str(out), "--exclude", "*.jpg",
               "--no-json-report", "--no-html-report"]
    )
    assert result.exit_code == 0, result.output
    assert (out / "forecast.pdf").exists()
    assert not (out / "photo.jpg").exists()


def test_clean_progress_bar_runs(dirty_tree, tmp_path):
    out = tmp_path / "cleaned"
    result = CliRunner().invoke(
        main, ["clean", str(dirty_tree), "--out", str(out), "--progress",
               "--no-json-report", "--no-html-report"]
    )
    assert result.exit_code == 0, result.output
    assert (out / "forecast.pdf").exists()


def test_debug_flag_reraises_instead_of_error_result(monkeypatch, dirty_pdf, tmp_path):
    from metascrub import cleaner

    real = cleaner.engine_for

    class _Boom:
        def __init__(self, e):
            self.name = e.name
        def probe(self, p, cfg=None):
            return []
        def strip(self, s, d, c):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(cleaner, "engine_for", lambda ext: _Boom(real(ext)))

    plain = CliRunner().invoke(main, ["clean", str(dirty_pdf), "--out", str(tmp_path / "a"),
                                      "--no-json-report", "--no-html-report"])
    assert plain.exit_code == 1                       # recorded as an errored file, batch continues

    dbg = CliRunner().invoke(main, ["--debug", "clean", str(dirty_pdf), "--out", str(tmp_path / "b"),
                                    "--no-json-report", "--no-html-report"])
    assert isinstance(dbg.exception, RuntimeError) and "kaboom" in str(dbg.exception)


def test_inspect_recurse_looks_inside_zip(dirty_pdf, tmp_path):
    import zipfile

    z = tmp_path / "bundle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(dirty_pdf, "inner/forecast.pdf")

    result = CliRunner().invoke(main, ["inspect", str(z), "--recurse", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    fields = {row["field"] for rows in data.values() for row in rows}
    assert any("Author" in f or "forecast.pdf" in f for f in fields)


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
