<p align="center"><sub>🇬🇧 English · <a href="ROADMAP.tr.md">🇹🇷 Türkçe</a></sub></p>

# MetaScrub roadmap

Where the project stands and what's next. Grouped by theme; roughly
ordered within each group. Nothing here is a promise — it's the working
backlog.

---

## Shipped since v0.1

- **Encrypted PDFs** — `metascrub clean --password …` / `inspect --password`.
  Without a password an encrypted PDF is a clean `skipped` (not a raw
  error); a wrong password is a clear `error`; the scrubbed copy is
  written unencrypted and the result says so. *(closes L4)*
- **PDF annotations** — reviewer name (`/T`), `/M` and `/CreationDate` are
  stripped from every markup annotation (and its `/Popup`); form-field
  widgets and the annotation's visible `/Contents` are left intact.
  *(part of L3)*
- **PDF embedded files** — the description and original timestamps on each
  attachment's file spec are removed; the attached file itself is kept.
  *(part of L3)*
- **`--strip-pdf-id`** — a fresh random trailer `/ID` on every run, so two
  scrubbed copies of one file can't be correlated by it. *(part of L3)*
- **Legacy `.doc / .xls / .ppt`** — `metascrub inspect` reads their
  `SummaryInformation` / `DocumentSummaryInformation` via `olefile`;
  `clean` converts them to `.docx/.xlsx/.pptx` with LibreOffice
  (`soffice`) and runs the normal Office scrubber over the result. No
  `soffice` on PATH → still `unsupported`, but with a message that says
  exactly why. `--in-place` is refused (the format changes). *(closes L1)*
- **SVG engine** — strips `<metadata>` (RDF/Dublin-Core author/title),
  `sodipodi:` / `inkscape:` / Adobe-Illustrator elements and attributes,
  and editor comments; the drawing is untouched. *(part of L7)*
- **`--backup`** — with `--in-place`, keeps the untouched original as
  `<name>.orig` (never clobbers an existing one).
- **`--strip-form-values`** *(opt-in)* — blanks PDF AcroForm field values
  (`/V`, `/DV`) and drops the cached `/AP` appearance so the old value
  can't still render; sets `NeedAppearances`. The name/address someone
  typed into a form is a leak even though it's technically content.
  *(closes L3)*
- **`--strip-office-authors`** *(opt-in)* — blanks tracked-change and
  comment **author names + dates** across `document.xml`,
  `comments.xml`, headers/footers, and the `people.xml` / `authors.xml` /
  `persons` registries (Word / PowerPoint / Excel); the change and
  comment *text* is kept so accept/reject still works. *(part of L5)*

---

## Known limitations

These are real gaps in the current release, not bugs:

| # | Gap | Notes |
|---|-----|-------|
| L2 | **Document *body* content is never touched** | Text typed into the document body, a comment's or tracked change's actual text, text baked into an image — out of scope by design (`--strip-form-values` / `--strip-office-authors` are the opt-in exceptions for the identity bits). |
| L5 | **Office: some parts still not covered** | `--strip-office-authors` now handles tracked-change / comment authors; still not touched: `docProps/thumbnail` in unusual layouts, external-link target paths, `.docm/.xlsm` `vbaProject.bin`. |
| L6 | **Images need the `exiftool` binary** | The Pillow fallback only does jpg/png/webp, drops the ICC profile unless kept, and can break animated formats. |
| L7 | **No audio / video engine** | SVG is handled now; `.mp4/.mov/.mp3/.m4a` still aren't (exiftool can — not yet wired up). |
| L11 | **Legacy Office needs LibreOffice** | `.doc/.xls/.ppt` scrubbing shells out to `soffice`; there's no pure-Python OLE2 rewriter, so without it those files stay `unsupported`. |
| L8 | **Verify pass is heuristic** | The "ignore structural tags" list in `engines/exiftool.py` is hand-maintained; no golden corpus asserts `residual == []` broadly yet. |
| L9 | **API/web have no authentication** | Documented, but there's no built-in token/key — you must front it with a proxy. |
| L10 | **Everything runs single-process, in-memory** | No parallelism for big trees; the API job registry is lost on restart. |

---

## Now — v0.2 (coverage + confidence)

- **Pure-Python legacy Office** — a minimal OLE2 property-stream rewriter
  so `.doc/.xls/.ppt` can be scrubbed without shelling out to LibreOffice.
  (would close L11)
- **Golden corpus** — a curated, license-clean set of real PDFs / Office
  docs / images checked into `tests/corpus/`, with a test that asserts every
  cleaned file re-scans to zero identifying metadata. (closes L8)
- **`metascrub diff <runA> <runB>`** — compare two run reports, like
  MetaScout's `diff`, to track a directory over time.
- CI: GitHub Actions matrix (Python 3.10–3.13 × macOS/Linux/Windows,
  with and without exiftool / LibreOffice), `ruff`, `mypy`.

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
