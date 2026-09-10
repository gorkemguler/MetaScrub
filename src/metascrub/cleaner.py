from __future__ import annotations

import contextlib
import datetime as _dt
import os
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .config import CleanConfig
from .engines import engine_for, tool_versions
from .models import BatchReport, CleanResult
from .scanner import iter_files

LogFn = Callable[[str], None]


def _noop_log(message: str) -> None:
    pass


def _overwrites_original(cfg: CleanConfig) -> bool:
    return cfg.in_place or bool(cfg.quarantine)


def clean_paths(
    roots: list[str],
    cfg: CleanConfig,
    *,
    base_dir: str | None = None,
    log: LogFn = _noop_log,
    on_result: Callable[[CleanResult], None] | None = None,
) -> BatchReport:
    """Scan `roots` for supported files and scrub each one per `cfg`.

    `on_result`, if given, is called once per file as it finishes (already
    serialised under the internal lock) — the CLI uses it to drive a
    progress bar.
    """
    files = iter_files(
        roots, cfg.filetypes, recursive=cfg.recursive,
        exclude=cfg.exclude, follow_symlinks=cfg.follow_symlinks,
    )
    report = BatchReport(
        root=base_dir or (roots[0] if roots else ""),
        in_place=_overwrites_original(cfg),
        dry_run=cfg.dry_run,
        tool_versions=tool_versions(),
    )
    if not files:
        log("! no supported files found")
        return report

    log(f"found {len(files)} file(s) to process")
    if not cfg.dry_run and not _overwrites_original(cfg):
        os.makedirs(cfg.output_dir, exist_ok=True)

    used_out_paths: set[str] = set()
    lock = threading.Lock()

    def _one(path: str) -> CleanResult:
        result = _clean_one(path, cfg, base_dir, used_out_paths, _locked(log, lock), lock)
        if on_result is not None:
            with lock:
                on_result(result)
        return result

    jobs = max(1, cfg.jobs)
    if jobs == 1 or len(files) == 1 or cfg.dry_run:
        report.results = [_one(p) for p in files]
    else:
        with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="metascrub") as ex:
            report.results = list(ex.map(_one, files))
    return report


def _locked(log: LogFn, lock: threading.Lock) -> LogFn:
    def _fn(message: str) -> None:
        with lock:
            log(message)
    return _fn


def clean_file_list(
    files: list[str],
    cfg: CleanConfig,
    *,
    base_dir: str | None = None,
    log: LogFn = _noop_log,
) -> BatchReport:
    """Like clean_paths but for an already-resolved list of individual
    files (used by the web UI / API, which hand us upload paths directly).
    """
    report = BatchReport(root=base_dir or "<uploads>", in_place=_overwrites_original(cfg),
                         dry_run=cfg.dry_run, tool_versions=tool_versions())
    if not cfg.dry_run and not _overwrites_original(cfg):
        os.makedirs(cfg.output_dir, exist_ok=True)
    used_out_paths: set[str] = set()
    for path in files:
        report.results.append(_clean_one(path, cfg, base_dir, used_out_paths, log))
    return report


def _clean_one(
    path: str,
    cfg: CleanConfig,
    base_dir: str | None,
    used_out_paths: set[str],
    log: LogFn,
    lock: threading.Lock | None = None,
) -> CleanResult:
    ext = _ext(path)
    engine = engine_for(ext)
    if engine is None:
        log(f"! {path}: unrecognised file type '.{ext}'")
        return CleanResult(src_path=path, filetype=ext, engine="?", status="unsupported",
                           reason=f"unrecognised file type '.{ext}'")

    overwrites = _overwrites_original(cfg)
    try:
        if cfg.dry_run:
            rows = engine.probe(path, cfg)
            log(f"{path}: {len(rows)} metadata field(s) (dry-run)")
            return CleanResult(
                src_path=path, filetype=ext, engine=engine.name, status="skipped",
                reason="dry-run", removed=rows,
                bytes_before=_size(path),
            )

        if overwrites:
            dst = path + ".metascrub-tmp"
        else:
            with (lock or _NULL_LOCK):
                dst = _dest_path(path, cfg.output_dir, base_dir, used_out_paths, cfg.overwrite)

        result = engine.strip(path, dst, cfg)

        if result.status == "cleaned" and result.out_path:
            if cfg.verify:
                # Re-dispatch by the *output* extension — an engine may
                # write a different format than it reads (legacy .doc -> .docx).
                verify_engine = engine_for(_ext(result.out_path)) or engine
                result.residual = [
                    f"{r.namespace}:{r.field}" for r in verify_engine.probe(result.out_path, cfg)
                ]
            if overwrites:
                if cfg.quarantine:
                    _quarantine(path, base_dir, cfg.quarantine)
                elif cfg.backup:
                    _make_backup(path)
                os.replace(result.out_path, path)
                result.out_path = path
                result.bytes_after = _size(path)
            log(f"{path}: removed {len(result.removed)} field(s)"
                + (f", {len(result.residual)} residual" if result.residual else ""))
        elif result.status == "skipped":
            _cleanup(dst)
            log(f"! {path}: skipped — {result.reason}")
        elif result.status == "unsupported":
            _cleanup(dst)
            log(f"! {path}: unsupported — {result.reason}")
        elif result.status == "error":
            _cleanup(dst)
            log(f"! {path}: error — {result.error}")
        return result

    except Exception as exc:  # noqa: BLE001 - one bad file must not abort the batch
        if cfg.debug:
            raise
        log(f"! {path}: {exc}")
        return CleanResult(src_path=path, filetype=ext, engine=engine.name, status="error",
                           error=str(exc), bytes_before=_size(path))


def _dest_path(
    src: str, output_dir: str, base_dir: str | None, used: set[str], overwrite: bool
) -> str:
    if base_dir and _is_within(src, base_dir):
        rel = os.path.relpath(src, base_dir)
    else:
        rel = os.path.basename(src)
    dst = os.path.join(output_dir, rel)

    stem, ext = os.path.splitext(dst)
    counter = 1
    while (dst in used) or (os.path.exists(dst) and not overwrite):
        dst = f"{stem}({counter}){ext}"
        counter += 1
    used.add(dst)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    return dst


def _is_within(path: str, root: str) -> bool:
    path = os.path.realpath(path)
    root = os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


_NULL_LOCK = contextlib.nullcontext()


def _make_backup(path: str) -> None:
    """Copy `path` to `path + '.orig'` before an in-place scrub, unless a
    backup is already there (never clobber an earlier original)."""
    dest = path + ".orig"
    if not os.path.exists(dest):
        shutil.copy2(path, dest)


def _quarantine(path: str, base_dir: str | None, quarantine_dir: str) -> None:
    """Move the untouched original into
    <quarantine_dir>/<YYYY-MM-DD>/<relpath> before it's overwritten."""
    if base_dir and _is_within(path, base_dir):
        rel = os.path.relpath(path, base_dir)
    else:
        rel = os.path.basename(path)
    dest = os.path.join(quarantine_dir, _dt.date.today().isoformat(), rel)
    stem, ext = os.path.splitext(dest)
    n = 1
    while os.path.exists(dest):
        dest = f"{stem}({n}){ext}"
        n += 1
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    shutil.copy2(path, dest)


def _cleanup(path: str | None) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _ext(name: str) -> str:
    base = os.path.basename(name)
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""
