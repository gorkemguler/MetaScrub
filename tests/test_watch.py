from __future__ import annotations

import os

import pikepdf
import pytest

from metacls.config import CleanConfig
from metacls.watch import Watcher, WatchLock, WatchLockError


def _dirty_pdf(path):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(100, 100))
    pdf.docinfo["/Author"] = "Watched Wanda"
    pdf.save(str(path))


def _watcher(directory, **kw):
    cfg = kw.pop("cfg", None) or CleanConfig(filetypes=["pdf"], verify=True)
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

    w2 = _watcher(tmp_path)              # fresh instance reads .metacls-watch.json
    assert w2.scan_once() == 0           # doesn't re-scrub


def test_pattern_filters_what_is_picked_up(tmp_path):
    _dirty_pdf(tmp_path / "invoice-01.pdf")
    _dirty_pdf(tmp_path / "scratch.pdf")

    w = _watcher(tmp_path, patterns=["invoice-*.pdf"])
    w.scan_once()
    assert w.scan_once() == 1            # only the matching file

    with pikepdf.open(str(tmp_path / "invoice-01.pdf")) as pdf:
        assert "/Info" not in pdf.trailer
    with pikepdf.open(str(tmp_path / "scratch.pdf")) as pdf:
        assert "/Info" in pdf.trailer    # left alone


def test_vanished_files_are_pruned_from_state(tmp_path):
    f = tmp_path / "drop.pdf"
    _dirty_pdf(f)
    w = _watcher(tmp_path)
    w.scan_once()
    w.scan_once()
    assert str(f) in w._done

    os.remove(f)
    w.scan_once()
    assert str(f) not in w._done         # entry dropped once the file is gone


def test_jobs_scrubs_a_backlog_in_one_pass(tmp_path):
    for i in range(4):
        _dirty_pdf(tmp_path / f"drop{i}.pdf")

    w = _watcher(tmp_path, cfg=CleanConfig(filetypes=["pdf"], verify=True, jobs=3))
    w.scan_once()
    assert w.scan_once() == 4
    for i in range(4):
        with pikepdf.open(str(tmp_path / f"drop{i}.pdf")) as pdf:
            assert "/Info" not in pdf.trailer


def test_lock_blocks_a_second_watcher_and_releases(tmp_path):
    with WatchLock(str(tmp_path)):
        assert os.path.exists(tmp_path / ".metacls-watch.lock")
        with pytest.raises(WatchLockError):
            WatchLock(str(tmp_path)).acquire()
    assert not os.path.exists(tmp_path / ".metacls-watch.lock")   # released on exit


def test_lock_steals_a_dead_owners_lockfile(tmp_path):
    lock_path = tmp_path / ".metacls-watch.lock"
    lock_path.write_text("999999\n")     # a PID that is not running
    with WatchLock(str(tmp_path)):
        assert lock_path.read_text().strip() == str(os.getpid())


def test_scan_ignores_the_lock_and_state_files(tmp_path):
    _dirty_pdf(tmp_path / "drop.pdf")
    (tmp_path / ".metacls-watch.lock").write_text("1\n")
    w = _watcher(tmp_path)
    w.scan_once()
    assert w.scan_once() == 1             # the .lock / .json are never treated as inputs
