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
- **Legacy `.doc / .xls / .ppt`** — a pure-Python, in-place scrubber
  (`engines/ole2.py`) patches the `\x05SummaryInformation` /
  `\x05DocumentSummaryInformation` property streams — author,
  last-saved-by, company, manager, template, title, timestamps and
  custom properties — without changing the file's size or structure, so
  the original format is kept and `--in-place` works. LibreOffice
  (`soffice`) is now only a *fallback* for a container the patcher can't
  parse (and it re-renders to OOXML). *(closes L1 and L11)*
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
- **`metascrub diff <runA> <runB>`** — compares two run reports (or run
  dirs): files added / removed, and — the point — files where metadata
  *reappeared* between runs (someone re-saved the document). Exit code 1
  when any file regained metadata, for monitoring a tree over time.
- **Golden corpus** — `tests/test_corpus.py` generates one deliberately
  dirty file per format (pdf/docx/xlsx/pptx/odt/ods/svg/jpg/doc) and
  asserts each scrubs to zero residual. *(closes L8)* It already caught a
  real bug — the ODF `probe` looked for `<meta>` in the wrong namespace,
  so `inspect` / dry-run / verify were blind to `.odt/.ods` metadata.
- **Tooling** — `ruff` + `mypy` (both clean), a GitHub Actions CI matrix
  (py 3.10–3.13 × Linux/macOS/Windows), a `slow` pytest marker + a
  session-scoped legacy-`.doc` fixture (`pytest -q` ~60 s → ~12 s),
  `CHANGELOG.md` / `CONTRIBUTING.md` / `SECURITY.md`.
- **API auth + limits** — `metascrub api --api-key` (env
  `METASCRUB_API_KEY`) required on every `/v1` route bar `/v1/health`, as
  `X-API-Key` or `Authorization: Bearer`. Uploads stream straight to a
  temp file (never the whole batch in memory) with `--max-upload-mb` /
  `--max-files` caps → 413. Both `web` and `api` **refuse to bind a
  non-loopback host** with no auth unless `--insecure`. *(closes L9)*
- **Durable API jobs** — the job registry is now a SQLite file
  (`<output_dir>/jobs.db`); job status + summary survive a restart, a job
  that was `running` when the process died comes back as `error:
  interrupted by a service restart`, and `--run-ttl-days N` prunes old
  finished jobs + their run dirs on startup. *(part of L10)*
- **Container** — the image runs as a non-root user (uid 1000), has a
  `HEALTHCHECK`, and `metascrub api --log-json` emits one JSON
  access-log line per request. `docker-compose` API service now takes
  `METASCRUB_API_KEY` and a 30-day TTL.
- **Audio / video** — a new `MediaEngine` (opt-in via `--media`). Audio
  (`mp3/m4a/flac/ogg/opus/wav/aiff`) uses `mutagen` — every tag and
  embedded cover art. Video (`mp4/mov/m4v/...`) uses exiftool to clear
  the metadata atoms while leaving the track structure alone. HEIC now
  also works through `pillow-heif` when exiftool is absent. *(closes L7;
  narrows L6)*

---

## Known limitations

These are real gaps in the current release, not bugs:

| # | Gap | Notes |
|---|-----|-------|
| L2 | **Document *body* content is never touched** | Text typed into the document body, a comment's or tracked change's actual text, text baked into an image — out of scope by design (`--strip-form-values` / `--strip-office-authors` are the opt-in exceptions for the identity bits). |
| L5 | **Office: some parts still not covered** | `--strip-office-authors` now handles tracked-change / comment authors; still not touched: `docProps/thumbnail` in unusual layouts, external-link target paths, `.docm/.xlsm` `vbaProject.bin`. |
| L6 | **Images: Pillow fallback is weak** | Only jpg/png/webp/heic (heic via `pillow-heif`), can break animated formats. exiftool is still the real path. |
| L7 | **Video scrub is best-effort** | Audio (`mutagen`) is thorough; for video only the metadata atoms are cleared — a container exiftool can't write (`.mkv`/`.avi`/`.webm` in places) may not be fully covered, and playback should be spot-checked. |
| L11 | **Legacy Office: format-internal usernames** | The OLE2 patcher clears the property streams (what `inspect` / Explorer show); it doesn't reach `.xls` `WRITEACCESS` or `.ppt` `CurrentUserAtom`. The LibreOffice fallback does (full re-render). |
| L8 | **exiftool ignore-list is hand-maintained** | `engines/exiftool.py`'s "structural tag" allow-list is still curated by hand; the golden corpus now guards the common cases but an exotic camera tag could slip through. |
| L10 | **Everything runs single-process, in-memory** | No parallelism for big trees; the API job registry is lost on restart. |

---

## Now — v0.3 (make it a service)

### Service hardening (the "run it on a Linux server / FTP box" story)
- Publish versioned images to GHCR from CI; optional `/metrics`.
- A documented nginx/Caddy reverse-proxy recipe next to `--api-key`.

### `metascrub watch` — the FTP/SFTP drop-box daemon — **done**
- `metascrub watch <dir> [--to DIR] [--move-processed DIR] [--interval] [--settle] [--once]`
- Polling loop with a settle window (no half-uploaded files), a JSON state
  file so restarts don't reprocess, re-drop detection, and a systemd
  template unit in `platform/linux/`.
- *Still to do:* inotify fast-path on Linux, and an SFTP mode that pulls
  from a remote drop dir and pushes the cleaned file back.

### Platform wrappers (the "right-click / plugin" story) — **first cut done**
- **macOS** — `platform/macos/install-quick-action.sh` builds a Finder
  Quick Action. *To do:* a signed drop-target `.app`, a Homebrew formula.
- **Windows** — `platform/windows/install-context-menu.ps1` adds an
  HKCU right-click entry. *To do:* an `IExplorerCommand` shell extension
  (for the Win11 top-level menu), a `winget` package.
- **Linux** — `platform/linux/nautilus-scrub-metadata.sh`. *To do:*
  Dolphin `.desktop` service menu, `.deb` / `.rpm` / AUR.

### CI / DevSecOps integration — **done**
- `metascrub clean --check` (exit 3 on metadata), a `.pre-commit-hooks.yaml`
  (`id: metascrub`), and a composite **GitHub Action** (`action.yml`,
  `check` / `fix` modes). *To do:* publish the action to the Marketplace,
  a GitLab CI template, and a PR-comment reporter.

## Later — v1.0 (polish + scale)

Shipped: `--jobs N` (thread-pool parallel scrub), `--quarantine DIR`,
`.metascrub.toml` project config, `--policy publish|internal|minimal`, a
collapsible/filterable/printable HTML report, and a
`release.yml` (tag → build → PyPI Trusted Publishing + GitHub Release).

Still open:
- A `rich` progress bar for large trees.
- A combined HTML report across runs; copy-as-CSV.
- Deeper video — EBML `Tags` for `.mkv/.webm`, RIFF `LIST` for `.avi`.
- Windows `IExplorerCommand` shell extension; `winget` / Homebrew /
  `.deb` packages; publish the GitHub Action to the Marketplace.

## Someday — bigger bets

- **Recursive containers** — *first cut done*: `metascrub clean --recurse`
  descends into `.zip` archives and `.eml` emails (`engines/container.py`),
  scrubs each member, repacks, depth-limited. Still open: `.msg` (Outlook),
  and re-embedding scrubbed copies of a PDF's *own* `/EmbeddedFiles`.
- **Content-side flagging** — call MetaScout's `--scan-content` on the
  output and warn if PII still sits in the *body* text. MetaScrub still
  won't edit content, but it can tell you it's there.
- **Deterministic rebuilds** — byte-identical output for the same input +
  options, so a scrub is reproducible/auditable.
