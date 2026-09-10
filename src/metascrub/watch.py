"""`metascrub watch` — keep a drop directory scrubbed.

Polls a directory (an FTP/SFTP landing zone, a shared folder). When a file
has stopped changing for `settle` seconds — so a half-finished upload is
never touched — it is scrubbed in place (or copied to `--to`), optionally
moving the original into `--move-processed`. A small JSON state file in the
watched directory records what's been handled so a restart doesn't
re-scrub everything; a file re-dropped with a newer mtime is handled
again.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import time
from collections.abc import Callable

from .cleaner import clean_paths
from .config import CleanConfig
from .scanner import iter_files

_STATE_NAME = ".metascrub-watch.json"
LogFn = Callable[[str], None]


def _noop(_m: str) -> None:
    pass


class Watcher:
    def __init__(
        self,
        directory: str,
        cfg: CleanConfig,
        *,
        interval: float = 5.0,
        settle: float = 2.0,
        to_dir: str | None = None,
        move_processed: str | None = None,
        recursive: bool = True,
        log: LogFn = _noop,
    ) -> None:
        self.dir = os.path.abspath(directory)
        self.cfg = cfg
        self.interval = interval
        self.settle = settle
        self.to_dir = os.path.abspath(to_dir) if to_dir else None
        self.move_processed = os.path.abspath(move_processed) if move_processed else None
        self.recursive = recursive
        self.log = log
        self._state_path = os.path.join(self.dir, _STATE_NAME)
        self._done: dict[str, float] = _load_state(self._state_path)
        self._pending: dict[str, tuple[float, float]] = {}  # path -> (mtime, size) seen last poll
        self._stop = False

    def stop(self, *_a) -> None:
        self._stop = True

    def run_forever(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        self.log(f"watching {self.dir} (every {self.interval}s, settle {self.settle}s)")
        while not self._stop:
            self.scan_once()
            for _ in range(int(self.interval * 10)):
                if self._stop:
                    break
                time.sleep(0.1)
        self.log("stopped")

    def scan_once(self) -> int:
        """One pass. Returns the number of files scrubbed this pass."""
        now = time.time()
        files = [f for f in iter_files([self.dir], self.cfg.filetypes, recursive=self.recursive)
                 if os.path.basename(f) != _STATE_NAME]
        ready: list[str] = []
        seen_now: dict[str, tuple[float, float]] = {}

        for path in files:
            try:
                st = os.stat(path)
            except OSError:
                continue
            key = (st.st_mtime, st.st_size)
            seen_now[path] = key
            if self._done.get(path) == st.st_mtime:
                continue  # already scrubbed at this mtime
            prev = self._pending.get(path)
            if prev == key and now - st.st_mtime >= self.settle:
                ready.append(path)
        self._pending = seen_now

        scrubbed = 0
        for path in ready:
            if self._scrub_one(path):
                scrubbed += 1
        if scrubbed:
            _save_state(self._state_path, self._done)
        return scrubbed

    def _scrub_one(self, path: str) -> bool:
        cfg = _clone(self.cfg)
        if self.to_dir:
            cfg.in_place = False
            cfg.output_dir = self.to_dir
        else:
            cfg.in_place = True

        report = clean_paths([path], cfg, base_dir=self.dir, log=self.log)
        if not report.results:
            return False
        r = report.results[0]
        if r.status == "error":
            self.log(f"! {path}: {r.error}")
            return False

        try:
            self._done[path] = os.stat(r.out_path or path).st_mtime
        except OSError:
            self._done[path] = time.time()

        if self.move_processed and r.status in ("cleaned", "skipped", "unsupported"):
            os.makedirs(self.move_processed, exist_ok=True)
            dest = _free_name(os.path.join(self.move_processed, os.path.basename(path)))
            try:
                shutil.move(path, dest)
                self._done.pop(path, None)
                self.log(f"moved original -> {dest}")
            except OSError as exc:
                self.log(f"! could not move {path}: {exc}")
        self.log(f"{path}: {r.status} ({len(r.removed)} field(s))")
        return True


def _load_state(path: str) -> dict[str, float]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {k: float(v) for k, v in data.get("processed", {}).items()}
    except (OSError, ValueError):
        return {}


def _save_state(path: str, done: dict[str, float]) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"processed": done}, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def _free_name(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{stem}({n}){ext}"):
        n += 1
    return f"{stem}({n}){ext}"


def _clone(cfg: CleanConfig) -> CleanConfig:
    from dataclasses import replace

    return replace(cfg)
