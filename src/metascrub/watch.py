"""`metascrub watch` — keep a drop directory scrubbed.

Polls a directory (an FTP/SFTP landing zone, a shared folder). When a file
has stopped changing for `settle` seconds — so a half-finished upload is
never touched — it is scrubbed in place (or copied to `--to`), optionally
moving the original into `--move-processed`. A small JSON state file in the
watched directory records what's been handled so a restart doesn't
re-scrub everything; a file re-dropped with a newer mtime is handled
again, and entries for files that have since vanished are pruned.

A lock file (`.metascrub-watch.lock`, holding the owner PID) keeps two
watchers off the same directory; a lock left by a dead process is stolen.
`--pattern GLOB` narrows what's picked up; `--jobs N` scrubs a backlog in
parallel.
"""
from __future__ import annotations

import fnmatch
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
_LOCK_NAME = ".metascrub-watch.lock"
_INTERNAL = frozenset({_STATE_NAME, _LOCK_NAME})
LogFn = Callable[[str], None]


def _noop(_m: str) -> None:
    pass


def _pid_alive(pid: int) -> bool:
    """True if `pid` is (or might still be) a running process — a liveness
    probe used to decide whether to steal a stale lock file.

    POSIX: the standard `os.kill(pid, 0)` idiom. **Not** used on Windows —
    there, signal `0` is `CTRL_C_EVENT`, so `os.kill(pid, 0)` doesn't
    check liveness, it *sends a real console control event*
    (`GenerateConsoleCtrlEvent`) to whatever process group `pid` happens
    to name. Windows instead gets a pure query via `OpenProcess`, which
    signals nothing. Inconclusive results are treated as "alive" — this
    only decides whether it's *safe* to steal the lock.
    """
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # exists but we can't signal it, or some other error
    return True


class WatchLockError(RuntimeError):
    """Raised when another live `metascrub watch` already owns the directory."""


class WatchLock:
    """A PID-stamped lock file so two watchers can't fight over one drop
    directory. A lock whose owner PID is gone is treated as stale and
    stolen, so a killed watcher never wedges the folder."""

    def __init__(self, directory: str) -> None:
        self.path = os.path.join(os.path.abspath(directory), _LOCK_NAME)
        self._held = False

    def acquire(self) -> None:
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if self._stale():
                    try:
                        os.unlink(self.path)
                    except OSError:
                        pass
                    continue
                raise WatchLockError(
                    f"another metascrub watch is already running on {os.path.dirname(self.path)!r} "
                    f"(lock file {self.path}); remove it by hand if that's not true"
                ) from None
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(f"{os.getpid()}\n")
                self._held = True
                return
        raise WatchLockError(f"could not acquire watch lock at {self.path}")

    def _stale(self) -> bool:
        try:
            with open(self.path, encoding="utf-8") as fh:
                pid = int((fh.read().strip() or "0").splitlines()[0])
        except (OSError, ValueError, IndexError):
            return True
        if pid <= 0:
            return True
        return not _pid_alive(pid)

    def release(self) -> None:
        if not self._held:
            return
        try:
            with open(self.path, encoding="utf-8") as fh:
                owner = int((fh.read().strip() or "0").splitlines()[0])
            if owner == os.getpid():
                os.unlink(self.path)
        except (OSError, ValueError, IndexError):
            pass
        self._held = False

    def __enter__(self) -> WatchLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


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
        patterns: list[str] | None = None,
        log: LogFn = _noop,
    ) -> None:
        self.dir = os.path.abspath(directory)
        self.cfg = cfg
        self.interval = interval
        self.settle = settle
        self.to_dir = os.path.abspath(to_dir) if to_dir else None
        self.move_processed = os.path.abspath(move_processed) if move_processed else None
        self.recursive = recursive
        self.patterns = [p for p in (patterns or []) if p]
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
        files = [
            f for f in iter_files([self.dir], self.cfg.filetypes, recursive=self.recursive)
            if os.path.basename(f) not in _INTERNAL and self._matches(f)
        ]
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

        pruned = self._prune_state()
        scrubbed = self._scrub_ready(ready) if ready else 0
        if scrubbed or pruned:
            _save_state(self._state_path, self._done)
        return scrubbed

    def _matches(self, path: str) -> bool:
        if not self.patterns:
            return True
        name = os.path.basename(path)
        return any(fnmatch.fnmatch(name, pat) for pat in self.patterns)

    def _prune_state(self) -> bool:
        """Drop state entries whose file is gone — otherwise a long-lived
        watcher's `.metascrub-watch.json` grows without bound."""
        gone = [p for p in self._done if not os.path.exists(p)]
        for p in gone:
            del self._done[p]
        if gone:
            self.log(f"pruned {len(gone)} stale state entr{'y' if len(gone) == 1 else 'ies'}")
        return bool(gone)

    def _scrub_ready(self, ready: list[str]) -> int:
        """Scrub every settled file in one `clean_paths` call so `--jobs`
        (cfg.jobs) can spread a backlog across the thread pool."""
        cfg = _clone(self.cfg)
        if self.to_dir:
            cfg.in_place = False
            cfg.output_dir = self.to_dir
        else:
            cfg.in_place = True

        report = clean_paths(ready, cfg, base_dir=self.dir, log=self.log)
        by_path = {os.path.realpath(r.src_path): r for r in report.results}

        scrubbed = 0
        for path in ready:
            r = by_path.get(os.path.realpath(path))
            if r is None:
                continue
            if r.status == "error":
                self.log(f"! {path}: {r.error}")
                continue

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
            scrubbed += 1
        return scrubbed


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
