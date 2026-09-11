"""Pull files from an FTP/FTPS server to scrub -- the web UI's "From FTP"
form and (future) CLI/API equivalents.

One-shot connect, walk, download, disconnect. Nothing is persisted:
the password lives only in this function call's arguments and is never
logged, written to the run's state, or included in an error message.
"""
from __future__ import annotations

import ftplib
import os
from dataclasses import dataclass, field


class FtpFetchError(RuntimeError):
    """A problem safe to show on the results page as-is -- never built
    from the password."""


@dataclass
class FtpFile:
    remote_path: str  # path relative to the given remote_dir (for display)
    local_path: str


@dataclass
class FtpFetchResult:
    files: list[FtpFile] = field(default_factory=list)
    skipped_other_types: int = 0  # matched no extension in `extensions`
    truncated: bool = False       # hit max_files before the tree was exhausted


def fetch_ftp(
    *,
    host: str,
    port: int = 21,
    username: str = "",
    password: str = "",
    remote_dir: str = "/",
    dest_dir: str,
    extensions: set[str],
    use_tls: bool = False,
    recursive: bool = True,
    max_files: int = 200,
    timeout: float = 30.0,
) -> FtpFetchResult:
    """Connect to `host`, walk `remote_dir` (optionally recursively),
    download every file whose extension is in `extensions` into
    `dest_dir` (mirroring the remote subdirectory layout), then
    disconnect. Raises FtpFetchError on connection/login failure or if
    nothing matched.
    """
    host = (host or "").strip()
    if not host:
        raise FtpFetchError("FTP host is required.")
    if not extensions:
        raise FtpFetchError("no file types enabled to fetch.")

    ftp_cls = ftplib.FTP_TLS if use_tls else ftplib.FTP
    try:
        ftp = ftp_cls(timeout=timeout)
        ftp.connect(host, port or 21, timeout=timeout)
        ftp.login(username or "anonymous", password or "")
        if use_tls:
            ftp.prot_p()  # type: ignore[attr-defined]  # encrypt the data channel too, not just the login
    except ftplib.all_errors as exc:
        raise FtpFetchError(f"could not connect/log in to {host}:{port or 21} ({exc}).") from exc

    result = FtpFetchResult()
    try:
        try:
            ftp.cwd(remote_dir or "/")
        except ftplib.all_errors as exc:
            raise FtpFetchError(f"could not open remote directory {remote_dir!r} ({exc}).") from exc
        _walk(ftp, "", dest_dir, extensions, recursive, max_files, result)
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            try:
                ftp.close()
            except ftplib.all_errors:
                pass

    if not result.files:
        hint = " (some were skipped -- none matched the enabled file types)" \
            if result.skipped_other_types else ""
        raise FtpFetchError(f"no matching files found under {remote_dir!r}{hint}.")
    return result


def upload_ftp(
    *,
    host: str,
    port: int = 21,
    username: str = "",
    password: str = "",
    remote_dir: str,
    files: list[tuple[str, str]],  # (remote_path relative to remote_dir, local_path)
    use_tls: bool = False,
    timeout: float = 30.0,
) -> int:
    """Upload each (remote_path, local_path) pair back under `remote_dir`,
    overwriting whatever is there -- used for the opt-in "write the
    scrubbed copies back to the same folder" toggle. Returns how many
    uploaded; a per-file failure is skipped rather than aborting the
    whole batch (the caller already has the cleaned files locally /
    downloadable regardless).
    """
    if not files:
        return 0
    ftp_cls = ftplib.FTP_TLS if use_tls else ftplib.FTP
    try:
        ftp = ftp_cls(timeout=timeout)
        ftp.connect(host, port or 21, timeout=timeout)
        ftp.login(username or "anonymous", password or "")
        if use_tls:
            ftp.prot_p()  # type: ignore[attr-defined]
        ftp.cwd(remote_dir or "/")
    except ftplib.all_errors as exc:
        raise FtpFetchError(f"could not reconnect to upload cleaned copies back ({exc}).") from exc

    uploaded = 0
    try:
        for remote_rel, local_path in files:
            parts = remote_rel.split("/")
            name = parts[-1]
            subdirs = parts[:-1]
            try:
                cur = ftp.pwd()
                for d in subdirs:
                    try:
                        ftp.cwd(d)
                    except ftplib.all_errors:
                        ftp.mkd(d)
                        ftp.cwd(d)
                with open(local_path, "rb") as fh:
                    ftp.storbinary(f"STOR {name}", fh)
                ftp.cwd(cur)
                uploaded += 1
            except ftplib.all_errors:
                try:
                    ftp.cwd(remote_dir or "/")
                except ftplib.all_errors:
                    pass
                continue
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            try:
                ftp.close()
            except ftplib.all_errors:
                pass
    return uploaded


def _is_dir(ftp: ftplib.FTP, name: str) -> bool:
    """Portable directory test: try to cd into it and back out. Works
    against servers that don't support MLSD/MLST."""
    try:
        cur = ftp.pwd()
    except ftplib.all_errors:
        return False
    try:
        ftp.cwd(name)
    except ftplib.all_errors:
        return False
    try:
        ftp.cwd(cur)
    except ftplib.all_errors:
        pass
    return True


def _walk(
    ftp: ftplib.FTP,
    rel: str,
    dest_dir: str,
    extensions: set[str],
    recursive: bool,
    max_files: int,
    result: FtpFetchResult,
) -> None:
    if len(result.files) >= max_files:
        result.truncated = True
        return
    try:
        names = [n.rsplit("/", 1)[-1] for n in ftp.nlst()]
    except ftplib.error_perm:
        return  # empty directory on many servers raises this -- not fatal

    for name in sorted(set(names)):
        if name in (".", ".."):
            continue
        if len(result.files) >= max_files:
            result.truncated = True
            return
        remote_rel = f"{rel}/{name}" if rel else name

        if _is_dir(ftp, name):
            if recursive:
                try:
                    ftp.cwd(name)
                except ftplib.all_errors:
                    continue
                _walk(ftp, remote_rel, dest_dir, extensions, recursive, max_files, result)
                try:
                    ftp.cwd("..")
                except ftplib.all_errors:
                    pass
            continue

        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in extensions:
            result.skipped_other_types += 1
            continue

        local_path = os.path.join(dest_dir, *remote_rel.split("/"))
        os.makedirs(os.path.dirname(local_path) or dest_dir, exist_ok=True)
        try:
            with open(local_path, "wb") as fh:
                ftp.retrbinary(f"RETR {name}", fh.write)
        except ftplib.all_errors:
            try:
                os.remove(local_path)
            except OSError:
                pass
            continue
        result.files.append(FtpFile(remote_path=remote_rel, local_path=local_path))
