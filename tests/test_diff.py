from __future__ import annotations

import json

from click.testing import CliRunner

from metacls.cli import main
from metacls.diff import diff_reports


def _report(files):
    return {"tool": "metacls", "files": files}


def _f(path, removed=(), residual=()):
    return {"src_path": path, "removed": [{"namespace": n, "field": fld, "before": "x"} for n, fld in removed],
            "residual": list(residual)}


def test_detects_new_and_removed_files():
    a = _report([_f("/a/one.pdf"), _f("/a/two.pdf")])
    b = _report([_f("/b/two.pdf"), _f("/b/three.pdf")])
    d = diff_reports(a, b)
    assert d.new_files == ["three.pdf"]
    assert d.removed_files == ["one.pdf"]


def test_detects_regained_metadata():
    a = _report([_f("/x/memo.docx", removed=[("docProps/core", "creator")])])
    b = _report([_f("/y/memo.docx", removed=[("docProps/core", "creator"), ("docProps/core", "lastModifiedBy")])])
    d = diff_reports(a, b)
    assert d.regained == {"memo.docx": ["docProps/core:lastModifiedBy"]}
    assert not d.cleared


def test_cli_diff_exit_1_on_regained(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(_report([_f("/x/f.pdf", removed=[("PDF Info", "Author")])])))
    (tmp_path / "b.json").write_text(json.dumps(_report([
        _f("/y/f.pdf", removed=[("PDF Info", "Author"), ("PDF Info", "Producer")])
    ])))
    r = CliRunner().invoke(main, ["diff", str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    assert r.exit_code == 1
    assert "regained metadata" in r.output


def test_cli_diff_accepts_run_dirs(tmp_path):
    for name in ("run1", "run2"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "report.json").write_text(json.dumps(_report([_f("/x/doc.pdf")])))
    r = CliRunner().invoke(main, ["diff", str(tmp_path / "run1"), str(tmp_path / "run2")])
    assert r.exit_code == 0
    assert "No changes" in r.output
