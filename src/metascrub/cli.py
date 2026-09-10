from __future__ import annotations

import json
import os
import sys

import click
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.table import Table

from .cleaner import clean_paths
from .config import DEFAULT_FILETYPES, POLICIES, CleanConfig
from .engines import engine_for, missing_dependencies
from .report import render_html_report, render_json_report
from .scanner import iter_files

console = Console()

# MetaScrub's own mark — "Slant" figlet, distinct from MetaScout's block
# banner, with an emerald wipe rule underneath.
_MARK = "#2dd4a7"
_BANNER = r"""
   __  ___     __        _____                 __
  /  |/  /__  / /_____ _/ ___/______  __ _____/ /
 / /|_/ / -_)/ __/ _ `/\__ \/ __/ // / // / _  /
/_/  /_/\__/ \__/\_,_/____/\__/\_,_/\_,_/\_,_/
              ─ scrub ───────────────────────────
"""

_STATUS_STYLE = {
    "cleaned": _MARK,
    "skipped": "yellow",
    "unsupported": "dim",
    "error": "bold red",
}


def _banner() -> None:
    console.print(f"[bold {_MARK}]{_BANNER}[/bold {_MARK}]")
    console.print("[dim]Bulk metadata scrubbing for PDF, Office and image files.[/dim]\n")


def _log(message: str) -> None:
    if message.startswith("!"):
        console.print(f"[yellow]{message}[/yellow]")
    else:
        console.print(f"[bold {_MARK}]›[/bold {_MARK}] {message}")


def _load_project_config() -> dict:
    """Find `.metascrub.toml` in the cwd or a parent and turn each table
    (`[clean]`, `[inspect]`, `[watch]`) into a click default_map entry.
    CLI flags and env vars still win — this only changes the *defaults*.
    """
    try:
        import tomllib
    except ModuleNotFoundError:  # py3.10
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            return {}

    here = os.getcwd()
    while True:
        candidate = os.path.join(here, ".metascrub.toml")
        if os.path.isfile(candidate):
            try:
                with open(candidate, "rb") as fh:
                    data = tomllib.load(fh)
            except (OSError, ValueError):
                return {}
            return {
                cmd: {k.replace("-", "_"): v for k, v in tbl.items()}
                for cmd, tbl in data.items() if isinstance(tbl, dict)
            }
        parent = os.path.dirname(here)
        if parent == here or os.path.isdir(os.path.join(here, ".git")):
            return {}
        here = parent


@click.group()
@click.version_option(package_name="metascrub")
@click.pass_context
def main(ctx: click.Context) -> None:
    """MetaScrub — strip metadata from PDF, Office and image files in bulk."""
    load_dotenv(find_dotenv(usecwd=True))
    ctx.default_map = _load_project_config()


# --------------------------------------------------------------------------- clean


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--filetypes", default=",".join(DEFAULT_FILETYPES), show_default=True,
              help="Comma-separated extensions to pick up when walking a directory.")
@click.option("--media", is_flag=True, default=False,
              help="Also pick up audio/video files (mp3, m4a, mp4, mov, mkv, ...).")
@click.option("--recursive/--no-recursive", default=True, show_default=True)
@click.option("--in-place", is_flag=True, default=False,
              help="Overwrite originals instead of writing cleaned copies (irreversible).")
@click.option("--backup", is_flag=True, default=False,
              help="With --in-place, keep the untouched original as <name>.orig.")
@click.option("--quarantine", default=None, type=click.Path(),
              help="Overwrite the original, but move it to QUARANTINE/<date>/ first (safer than --in-place).")
@click.option("--jobs", "-j", default=1, show_default=True, help="Scrub this many files in parallel.")
@click.option("--out", "output_dir", default="./metascrub_cleaned", show_default=True,
              envvar="METASCRUB_OUTPUT_DIR", type=click.Path(),
              help="Where cleaned copies and the run report are written.")
@click.option("--keep", "keep_fields", multiple=True, metavar="FIELD",
              help="Metadata field to preserve, e.g. --keep Title (repeatable).")
@click.option("--dry-run", is_flag=True, default=False, help="Only show what would be removed.")
@click.option("--verify/--no-verify", default=True, show_default=True,
              help="Re-scan each cleaned file and report anything still present.")
@click.option("--keep-color-profile/--no-keep-color-profile", default=True, show_default=True)
@click.option("--keep-orientation/--no-keep-orientation", default=True, show_default=True)
@click.option("--overwrite", is_flag=True, default=False,
              help="Allow a cleaned copy to overwrite an existing file at the output path.")
@click.option("--password", "pdf_password", default=None,
              help="Password to open encrypted PDFs (the cleaned copy is written unencrypted).")
@click.option("--strip-pdf-id", is_flag=True, default=False,
              help="Give each scrubbed PDF a fresh random /ID so copies can't be correlated by it.")
@click.option("--strip-form-values", is_flag=True, default=False,
              help="Also blank PDF form-field values (/V, /DV) — user-entered data, not just metadata.")
@click.option("--strip-office-authors", is_flag=True, default=False,
              help="Also blank Office tracked-change / comment author names and dates (text is kept).")
@click.option("--json-report/--no-json-report", default=True, show_default=True)
@click.option("--html-report/--no-html-report", default=True, show_default=True)
@click.option("--report-lang", type=click.Choice(["en", "tr"]), default="en", show_default=True,
              envvar="METASCRUB_REPORT_LANG")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip the --in-place confirmation.")
@click.option("--check", is_flag=True, default=False,
              help="Implies --dry-run; exit 3 if any file still carries metadata (pre-commit / CI gate).")
@click.option("--policy", type=click.Choice(sorted(POLICIES)), default=None,
              help="Named preset: publish (all opt-ins), internal (keep titles), minimal (default).")
@click.pass_context
def clean(ctx, paths, filetypes, media, recursive, in_place, backup, quarantine, jobs, output_dir,
          keep_fields, dry_run, verify, keep_color_profile, keep_orientation, overwrite, pdf_password,
          strip_pdf_id, strip_form_values, strip_office_authors, json_report, html_report,
          report_lang, yes, check, policy):
    """Scrub metadata from every supported file in PATHS (files and/or directories).

    By default originals are left untouched and cleaned copies are written
    under --out, mirroring the input directory tree. Use --in-place to
    overwrite the originals instead.
    """
    ft_list = [f.strip().lower().lstrip(".") for f in filetypes.split(",") if f.strip()]
    if media:
        from .config import MEDIA_EXTENSIONS
        ft_list = sorted(set(ft_list) | MEDIA_EXTENSIONS)
    roots = [os.fspath(p) for p in paths]
    base_dir = _common_base(roots)
    if check:
        dry_run = True
    if policy:
        cmdline = click.core.ParameterSource.COMMANDLINE
        for name, value in POLICIES[policy].items():
            if ctx.get_parameter_source(name) != cmdline:
                if name == "keep_fields":
                    keep_fields = tuple(keep_fields) + tuple(value)
                elif name == "strip_pdf_id":
                    strip_pdf_id = value
                elif name == "strip_form_values":
                    strip_form_values = value
                elif name == "strip_office_authors":
                    strip_office_authors = value

    cfg = CleanConfig(
        filetypes=ft_list, recursive=recursive, in_place=in_place, output_dir=output_dir,
        keep_fields=list(keep_fields), dry_run=dry_run, verify=verify,
        keep_color_profile=keep_color_profile, keep_orientation=keep_orientation,
        overwrite=overwrite, pdf_password=pdf_password, strip_pdf_id=strip_pdf_id,
        backup=backup, strip_form_values=strip_form_values,
        strip_office_authors=strip_office_authors, quarantine=quarantine, jobs=jobs,
    )

    _banner()
    for warning in missing_dependencies(set(ft_list)):
        console.print(f"[yellow]! {warning}[/yellow]")

    if in_place and not dry_run and not yes:
        n = len(iter_files(roots, ft_list, recursive=recursive))
        if n and not click.confirm(
            f"--in-place will overwrite {n} original file(s) with scrubbed versions. Continue?"
        ):
            console.print("[yellow]Aborted.[/yellow]")
            sys.exit(1)

    report = clean_paths(roots, cfg, base_dir=base_dir, log=_log)

    if not report.results:
        console.print("[yellow]No supported files found. Nothing to do.[/yellow]")
        sys.exit(0)

    console.print()
    _print_table(report, base_dir)

    if json_report or html_report:
        os.makedirs(output_dir, exist_ok=True)
    if json_report:
        p = os.path.join(output_dir, "report.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(render_json_report(report))
        console.print(f"\n[green]JSON report:[/green] {p}")
    if html_report:
        p = os.path.join(output_dir, "report.html")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(render_html_report(report, lang=report_lang))
        console.print(f"[green]HTML report:[/green] {p}")

    if report.errored:
        console.print(f"\n[bold red]{len(report.errored)} file(s) errored.[/bold red]")
        sys.exit(1)
    if check:
        dirty = [r for r in report.results if r.removed]
        if dirty:
            console.print(
                f"\n[bold yellow]{len(dirty)} file(s) carry metadata "
                f"({report.fields_removed} field(s)).[/bold yellow] Run `metascrub clean` on them."
            )
            sys.exit(3)
        console.print("\n[green]No metadata found.[/green]")
        return
    if not dry_run and report.files_with_residual:
        console.print(
            f"\n[bold yellow]{len(report.files_with_residual)} file(s) still carry metadata "
            "after cleaning — verify manually.[/bold yellow]"
        )
        sys.exit(2)


def _print_table(report, base_dir) -> None:
    table = Table(title="MetaScrub — scrub results")
    table.add_column("File", overflow="fold")
    table.add_column("Type")
    table.add_column("Engine")
    table.add_column("Removed", justify="right")
    table.add_column("Residual", justify="right")
    table.add_column("Status")
    for r in sorted(report.results, key=lambda x: (x.status != "error", x.src_path)):
        shown = os.path.relpath(r.src_path, base_dir) if base_dir else r.src_path
        style = _STATUS_STYLE.get(r.status, "")
        residual = f"[red]{len(r.residual)}[/red]" if r.residual else "0"
        detail = f" [dim]{r.reason or r.error or ''}[/dim]" if (r.reason or r.error) else ""
        table.add_row(
            shown, f".{r.filetype}", r.engine, str(len(r.removed)), residual,
            f"[{style}]{r.status}[/{style}]{detail}" if style else f"{r.status}{detail}",
        )
    console.print(table)

    counts = report.counts
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    verb = "would be removed" if report.dry_run else "removed"
    console.print(f"[dim]{len(report.results)} file(s) — {summary} — "
                  f"{report.fields_removed} metadata field(s) {verb}[/dim]")


# --------------------------------------------------------------------------- inspect


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--filetypes", default=",".join(DEFAULT_FILETYPES), show_default=True)
@click.option("--recursive/--no-recursive", default=True, show_default=True)
@click.option("--password", "pdf_password", default=None, help="Password for encrypted PDFs.")
@click.option("--strip-form-values", is_flag=True, default=False,
              help="Also list PDF form-field values (shown only with this flag — they can be bulky).")
@click.option("--strip-office-authors", is_flag=True, default=False,
              help="Also list Office tracked-change / comment author names.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON instead of tables.")
def inspect(paths, filetypes, recursive, pdf_password, strip_form_values, strip_office_authors, as_json):
    """Show the metadata each file in PATHS currently carries. Read-only —
    writes nothing. Use this on the files MetaScout flagged to see exactly
    what's in them before scrubbing.
    """
    ft_list = [f.strip().lower().lstrip(".") for f in filetypes.split(",") if f.strip()]
    insp_cfg = CleanConfig(pdf_password=pdf_password, strip_form_values=strip_form_values,
                           strip_office_authors=strip_office_authors)
    files = iter_files([os.fspath(p) for p in paths], ft_list, recursive=recursive)

    if not files:
        console.print("[yellow]No supported files found.[/yellow]")
        sys.exit(0)

    out: dict[str, list[dict]] = {}
    for path in files:
        engine = engine_for(path.rsplit(".", 1)[-1] if "." in path else "")
        rows = []
        if engine is not None:
            try:
                rows = [{"namespace": c.namespace, "field": c.field, "value": c.before}
                        for c in engine.probe(path, insp_cfg)]
            except Exception as exc:  # noqa: BLE001
                rows = [{"namespace": "!", "field": "error", "value": str(exc)}]
        out[path] = rows

    if as_json:
        console.print_json(json.dumps(out, ensure_ascii=False))
        return

    _banner()
    for path, rows in out.items():
        console.print(f"[bold {_MARK}]▸ {path}[/bold {_MARK}]")
        if not rows:
            console.print("[green]  No metadata found.[/green]\n")
            continue
        table = Table(show_header=True, header_style="dim")
        table.add_column("Group")
        table.add_column("Field")
        table.add_column("Value", overflow="fold")
        for row in rows:
            table.add_row(row["namespace"], row["field"], row["value"])
        console.print(table)
        console.print()


# --------------------------------------------------------------------------- diff


@main.command()
@click.argument("run_a", type=click.Path(exists=True))
@click.argument("run_b", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, default=False)
def diff(run_a, run_b, as_json):
    """Compare two `metascrub clean` runs (report.json files or run dirs).

    Shows files added/removed between the two, and — the useful bit for
    monitoring a directory over time — files where metadata *reappeared*
    (someone re-saved the document in an editor). Exit code 1 if any file
    regained metadata.
    """
    from .diff import diff_reports, load_report

    d = diff_reports(load_report(os.fspath(run_a)), load_report(os.fspath(run_b)))

    if as_json:
        console.print_json(json.dumps({
            "new_files": d.new_files, "removed_files": d.removed_files,
            "regained": d.regained, "cleared": d.cleared, "residual_new": d.residual_new,
        }))
    else:
        _banner()
        if not d.any_changes:
            console.print("[green]No changes between the two runs.[/green]")
        if d.new_files:
            console.print(f"[bold]New files[/bold] ({len(d.new_files)}): " + ", ".join(d.new_files))
        if d.removed_files:
            console.print(f"[dim]Gone[/dim] ({len(d.removed_files)}): " + ", ".join(d.removed_files))
        for name, fields in d.regained.items():
            console.print(f"[bold red]⚠ {name}[/bold red] regained metadata: " + ", ".join(fields))
        for name, fields in d.residual_new.items():
            console.print(f"[yellow]⚠ {name}[/yellow] new residual: " + ", ".join(fields))
        for name, fields in d.cleared.items():
            console.print(f"[dim]{name} no longer carried: " + ", ".join(fields) + "[/dim]")

    if d.regained or d.residual_new:
        sys.exit(1)


# --------------------------------------------------------------------------- watch


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--filetypes", default=",".join(DEFAULT_FILETYPES), show_default=True)
@click.option("--recursive/--no-recursive", default=True, show_default=True)
@click.option("--to", "to_dir", default=None, type=click.Path(),
              help="Write cleaned copies here instead of scrubbing in place.")
@click.option("--move-processed", default=None, type=click.Path(),
              help="Move each original here after it's scrubbed.")
@click.option("--interval", default=5.0, show_default=True, help="Seconds between scans.")
@click.option("--settle", default=2.0, show_default=True,
              help="A file must be unchanged this long before it's touched (half-finished uploads).")
@click.option("--once", is_flag=True, default=False, help="Scan once and exit (for cron).")
@click.option("--keep", "keep_fields", multiple=True, metavar="FIELD")
@click.option("--strip-pdf-id", is_flag=True, default=False)
@click.option("--strip-form-values", is_flag=True, default=False)
@click.option("--strip-office-authors", is_flag=True, default=False)
@click.option("--backup", is_flag=True, default=False, help="Keep <name>.orig when scrubbing in place.")
@click.option("--verify/--no-verify", default=True, show_default=True)
def watch(directory, filetypes, recursive, to_dir, move_processed, interval, settle, once,
          keep_fields, strip_pdf_id, strip_form_values, strip_office_authors, backup, verify):
    """Keep DIRECTORY scrubbed — a poll loop for an FTP/SFTP drop folder.

    A file is only touched once it has stopped changing for --settle
    seconds, so a partial upload is safe. State is kept in
    DIRECTORY/.metascrub-watch.json so a restart doesn't re-scrub
    everything; a file re-dropped with a newer timestamp is handled again.
    """
    from .watch import Watcher

    ft_list = [f.strip().lower().lstrip(".") for f in filetypes.split(",") if f.strip()]
    cfg = CleanConfig(
        filetypes=ft_list, recursive=recursive, keep_fields=list(keep_fields), verify=verify,
        strip_pdf_id=strip_pdf_id, strip_form_values=strip_form_values,
        strip_office_authors=strip_office_authors, backup=backup,
    )
    w = Watcher(directory, cfg, interval=interval, settle=settle, to_dir=to_dir,
                move_processed=move_processed, recursive=recursive, log=_log)

    _banner()
    if once:
        n = w.scan_once()
        console.print(f"[dim]scrubbed {n} file(s)[/dim]")
        return
    console.print(f"[bold]MetaScrub watch[/bold] on [bold]{w.dir}[/bold] — Ctrl-C to stop\n")
    w.run_forever()


# --------------------------------------------------------------------------- web / api

_LOOPBACK = {"127.0.0.1", "localhost", "::1", ""}


def _loopback_guard(host: str, protected: bool, insecure: bool, what: str) -> None:
    """Refuse to bind a non-loopback address without either an auth
    mechanism (`protected`) or an explicit --insecure."""
    if host in _LOOPBACK or protected or insecure:
        return
    console.print(
        f"[bold red]Refusing to bind {what} to {host} with no authentication.[/bold red]\n"
        "Neither the web UI nor the API has a login. Put an authenticating reverse proxy in\n"
        "front, use `--api-key` (API only), stay on 127.0.0.1, or pass --insecure to override."
    )
    sys.exit(2)


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8770, show_default=True)
@click.option("--output-dir", default="./metascrub_cleaned", show_default=True,
              envvar="METASCRUB_OUTPUT_DIR", type=click.Path())
@click.option("--open-browser/--no-open-browser", default=True)
@click.option("--insecure", is_flag=True, default=False,
              help="Allow binding a non-loopback host despite there being no authentication.")
def web(host, port, output_dir, open_browser, insecure):
    """Launch the local drag-and-drop web UI."""
    from .web import run_server

    _banner()
    _loopback_guard(host, protected=False, insecure=insecure, what="the web UI")
    console.print(f"[bold]MetaScrub web UI[/bold] on [bold]http://{host}:{port}/[/bold]")
    console.print("[dim]No authentication — keep it on 127.0.0.1 or behind a proxy.[/dim]\n")
    run_server(host=host, port=port, output_dir=output_dir, open_browser=open_browser)


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Use 0.0.0.0 to accept connections from other machines — read the README first.")
@click.option("--port", default=8000, show_default=True)
@click.option("--output-dir", default="./metascrub_cleaned", show_default=True,
              envvar="METASCRUB_OUTPUT_DIR", type=click.Path())
@click.option("--max-workers", default=2, show_default=True)
@click.option("--max-pending", default=50, show_default=True)
@click.option("--api-key", envvar="METASCRUB_API_KEY", default=None,
              help="Require this key on every /v1 route (X-API-Key or Bearer) except /v1/health.")
@click.option("--max-upload-mb", default=200, show_default=True, help="Cap on a single request's total upload.")
@click.option("--max-files", default=50, show_default=True, help="Cap on files per request.")
@click.option("--run-ttl-days", default=0, show_default=True,
              help="Delete finished jobs + their run dirs older than N days on startup (0 = keep).")
@click.option("--log-json", is_flag=True, default=False, help="Emit one JSON access-log line per request.")
@click.option("--insecure", is_flag=True, default=False,
              help="Allow binding a non-loopback host with no --api-key.")
def api(host, port, output_dir, max_workers, max_pending, api_key, max_upload_mb, max_files,
        run_ttl_days, log_json, insecure):
    """Launch the MetaScrub REST API (job-based). Requires: pip install 'metascrub[api]'."""
    try:
        import uvicorn

        from .api import create_app
    except ImportError:
        console.print("[bold red]Missing dependency.[/bold red] Install the API extra first:")
        console.print("  pip install 'metascrub[api]'")
        sys.exit(1)

    _banner()
    _loopback_guard(host, protected=bool(api_key), insecure=insecure, what="the API")
    auth = "API key required" if api_key else "NO authentication"
    console.print(f"[bold]MetaScrub API[/bold] on [bold]http://{host}:{port}/[/bold]  (docs: /docs) — {auth}")
    app = create_app(output_dir=output_dir, max_workers=max_workers, max_pending=max_pending,
                     api_key=api_key, max_upload_mb=max_upload_mb, max_files=max_files,
                     run_ttl_days=run_ttl_days, log_json=log_json)
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _common_base(roots: list[str]) -> str | None:
    candidates = [r if os.path.isdir(r) else os.path.dirname(r) or "." for r in roots]
    try:
        base = os.path.commonpath([os.path.abspath(c) for c in candidates])
    except ValueError:
        return None
    return base if os.path.isdir(base) else None


if __name__ == "__main__":
    main()
