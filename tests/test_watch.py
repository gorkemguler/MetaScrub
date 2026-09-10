from __future__ import annotations

import pikepdf

from metascrub.config import CleanConfig
from metascrub.watch import Watcher


def _dirty_pdf(path):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(100, 100))
    pdf.docinfo["/Author"] = "Watched Wanda"
    pdf.save(str(path))


def _watcher(directory, **kw):
    cfg = CleanConfig(filetypes=["pdf"], verify=True)
    return Watcher(str(directory), cfg, settle=0.0, log=lambda m: None, **kw)


def test_scrubs_a_settled_file_in_place(tmp_path):
    f = tmp_path / "drop.pdf"
    _dirty_pdf(f)

    w = _watcher(tmp_path)
    assert w.scan_once() == 0          # first sight: not yet "settled" (no prior observation)
    assert w.scan_once() == 1          # seen unchanged since last poll -> scrubbed

    with pikepdf.open(str(f)) as pdf:
        assert "/Info" not in pdf.trailer
    assert w.scan_once() == 0          # already done, not touched again


def test_redropped_file_is_rescrubbed(tmp_path):
    f = tmp_path / "drop.pdf"
    _dirty_pdf(f)
    w = _watcher(tmp_path)
    w.scan_once()
    w.scan_once()
    assert w.scan_once() == 0

    import os
    import time

    _dirty_pdf(f)                       # same name, new content
    os.utime(f, (time.time() - 5, time.time() - 5))   # a distinct, already-settled mtime
    w.scan_once()                       # observe it
    assert w.scan_once() == 1           # stable since last poll -> re-scrubbed


def test_to_dir_leaves_original(tmp_path):
    src = tmp_path / "in"
    out = tmp_path / "out"
    src.mkdir()
    f = src / "drop.pdf"
    _dirty_pdf(f)
    before = f.read_bytes()

    w = _watcher(src, to_dir=str(out))
    w.scan_once()
    w.scan_once()

    assert f.read_bytes() == before                     # original untouched
    cleaned = out / "drop.pdf"
    assert cleaned.is_file()
    with pikepdf.open(str(cleaned)) as pdf:
        assert "/Info" not in pdf.trailer


def test_move_processed(tmp_path):
    src = tmp_path / "in"
    archive = tmp_path / "done"
    src.mkdir()
    _dirty_pdf(src / "drop.pdf")

    w = _watcher(src, move_processed=str(archive))
    w.scan_once()
    w.scan_once()

    assert not (src / "drop.pdf").exists()
    assert (archive / "drop.pdf").is_file()


def test_state_file_survives_new_watcher(tmp_path):
    _dirty_pdf(tmp_path / "drop.pdf")
    w1 = _watcher(tmp_path)
    w1.scan_once()
    w1.scan_once()

    w2 = _watcher(tmp_path)              # fresh instance reads .metascrub-watch.json
    assert w2.scan_once() == 0           # doesn't re-scrub
