<p align="center"><sub>🇬🇧 English · <a href="ROADMAP.tr.md">🇹🇷 Türkçe</a></sub></p>

# MetaScrub roadmap

Where v0.1 stands and what's next. Grouped by theme; roughly ordered
within each group. Nothing here is a promise — it's the working backlog.

---

## Known limitations in v0.1

These are real gaps in the current release, not bugs:

| # | Gap | Notes |
|---|-----|-------|
| L1 | **Legacy `.doc / .xls / .ppt` not scrubbed** | Reported as `unsupported`. No safe stdlib-only strip for OLE2 Compound File Binary. |
| L2 | **Document content is never touched** | Author names in tracked changes / comments, text typed into the body, text baked into an image — all out of scope by design. |
| L3 | **PDF: only `/Info` + XMP + `/PieceInfo` + page metadata** | Not yet handled: embedded-file attachments, annotation authors/dates, AcroForm data, `xmpMM` edit history, the trailer `/ID`. |
| L4 | **Encrypted / password PDFs land as `error`** | pikepdf can't open them without the password; there's no `--password` flag yet. |
| L5 | **Office: only `docProps/*` + `w:rsids`** | Not yet: tracked-change/comment authors, `docProps/thumbnail` in some layouts, external-link paths, `.docm/.xlsm` `vbaProject.bin`. |
| L6 | **Images need the `exiftool` binary** | The Pillow fallback only does jpg/png/webp, drops the ICC profile unless kept, and can break animated formats. |
| L7 | **No SVG / audio / video engine** | `.svg` (editor comments, `<metadata>`), `.mp4/.mov/.mp3/.m4a` (exiftool can, we don't wire it up). |
| L8 | **Verify pass is heuristic** | The "ignore structural tags" list in `engines/exiftool.py` is hand-maintained; no golden corpus asserts `residual == []` broadly yet. |
| L9 | **API/web have no authentication** | Documented, but there's no built-in token/key — you must front it with a proxy. |
| L10 | **Everything runs single-process, in-memory** | No parallelism for big trees; the API job registry is lost on restart. |

---

## Now — v0.2 (coverage + confidence)

- **PDF depth** — embedded-file attachments (`/Names /EmbeddedFiles`, `/AF`),
  annotation `/T` `/M` `/CreationDate`, `xmpMM:History` / `xmpMM:DerivedFrom`,
  a `--strip-id` flag for the trailer `/ID`. (closes L3)
- **Encrypted PDFs** — detect and report clearly instead of a raw error; add
  `metascrub clean --password …`. (closes L4)
- **Legacy Office** — `olefile`-based zeroing of `\x05SummaryInformation` /
  `\x05DocumentSummaryInformation`, with an optional LibreOffice-headless
  convert-and-back path when `soffice` is present. (closes L1)
- **Office authors** — opt-in `--strip-office-authors`: `w:ins`/`w:del`
  authors, `comments.xml` / `people.xml`, PowerPoint notes. (part of L5)
- **SVG engine** — strip `<metadata>`, editor comments, `sodipodi:`/`inkscape:`
  attributes. (part of L7)
- **Golden corpus** — a curated, license-clean set of real PDFs / Office
  docs / images checked into `tests/corpus/`, with a test that asserts every
  cleaned file re-scans to zero identifying metadata. (closes L8)
- **`--backup`** — keep `<name>.orig` next to an `--in-place` scrub.
- **`metascrub diff <runA> <runB>`** — compare two run reports, like
  MetaScout's `diff`, to track a directory over time.
- CI: GitHub Actions matrix (Python 3.10–3.13 × macOS/Linux/Windows,
  with and without exiftool), `ruff`, `mypy`.

## Next — v0.3–v0.5 (make it a service, make it fit in)

### Service hardening (the "run it on a Linux server / FTP box" story)
- **Auth for the API** — static API-key header + a documented nginx/Caddy
  reverse-proxy recipe; refuse to bind non-loopback without one unless
  `--i-know` is passed. (closes L9)
- **Streaming uploads** — write request bodies straight to disk instead of
  `await f.read()` into memory; per-request file-count and size caps.
- **Durable jobs** — SQLite-backed job registry so status/logs survive a
  restart; TTL cleanup of old run directories. (part of L10)
- **Container** — non-root user, `HEALTHCHECK`, versioned images published
  to GHCR, `docker scout` clean.
- Structured JSON logging; optional `/metrics`.

### `metascrub watch` — the FTP/SFTP drop-box daemon
- `metascrub watch <dir> [--pattern] [--in-place | --to <dir>] [--move-back]`
- inotify (Linux) / polling fallback, debounce, lockfile, systemd unit.
- Optional SFTP mode: pull from a remote drop dir, scrub, push back.

### Platform wrappers (the "right-click / plugin" story)
- **macOS** — a Quick Action (`.workflow`) so *Finder → right-click → Clean
  metadata* and the Services menu both call the CLI; a small SwiftUI
  drop-target `.app`; a Homebrew formula.
- **Windows** — an Explorer context-menu entry (`IExplorerCommand` shell
  extension), a `winget` package, a PowerShell module.
- **Linux** — Nautilus / Dolphin / Thunar custom-action scripts; `.deb` /
  `.rpm` / AUR.

### CI / DevSecOps integration
- A `pre-commit` hook that runs `metascrub clean --dry-run` and fails the
  commit on dirty documents.
- A published **GitHub Action** (`gorkemguler/metascrub-action`) — runs on a
  PR, posts the report as a comment, optionally auto-commits cleaned files.
- A GitLab CI template.

## Later — v1.0 (polish + scale)

- **Parallelism** — `--jobs N` (ProcessPoolExecutor) for large trees; a
  `rich` progress bar. (closes L10)
- **`--quarantine`** — move originals to a dated folder rather than deleting
  them, as a safer default than `--in-place`.
- **Project config** — `.metascrub.toml` for per-repo keep-lists and
  defaults.
- **Policy profiles** — `--policy publish` / `--policy internal` etc., each a
  documented, named set of fields to remove/keep.
- **HTML report** — collapsible cards, filter by status, copy-as-CSV, a
  print stylesheet; a combined report across multiple runs.
- Audio / video engine behind `--media`. (closes L7)
- HEIC without exiftool (via `pillow-heif`). (part of L6)
- PyPI release, `v0.1.0` tag + GitHub release + `CHANGELOG.md`,
  `SECURITY.md`, `CONTRIBUTING.md`.

## Someday — bigger bets

- **Recursive containers** — a PDF with an attached `.docx`, a `.zip` of
  documents, an `.eml` / `.msg` with attachments: descend and scrub each
  part, repackage.
- **Content-side flagging** — call MetaScout's `--scan-content` on the
  output and warn if PII still sits in the *body* text. MetaScrub still
  won't edit content, but it can tell you it's there.
- **Deterministic rebuilds** — byte-identical output for the same input +
  options, so a scrub is reproducible/auditable.
