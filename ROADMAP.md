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
| L5 | **Office: some parts still not covered** | `--strip-office-authors` handles tracked-change / comment authors; macro-enabled / template files scrub and flag `vbaProject.bin`. Still not touched: the *contents* of `vbaProject.bin` (kept on purpose), external-link target paths, and `docProps/thumbnail` in unusual layouts. |
| L6 | **Images: Pillow fallback is weak** | exiftool handles jpg/png/gif/webp/heic/tiff thoroughly. The Pillow fallback (no exiftool) is only jpg/png/webp/heic (heic via `pillow-heif`) and can break animated formats. |
| L7 | **Video scrub is best-effort** | Audio (`mutagen`) is thorough. MP4-family video: exiftool clears the metadata atoms. Matroska / WebM / AVI: the `Tags` / `Info` / `LIST INFO` / `IDIT` metadata is blanked in place (`engines/ebml_riff.py`), but a `Tags` element sitting *after* an unknown-size Cluster isn't reached, and `Chapters` / attachment names are left alone. Spot-check playback. |
| L11 | **Legacy Office: format-internal usernames** | The OLE2 patcher clears the property streams (what `inspect` / Explorer show); it doesn't reach `.xls` `WRITEACCESS` or `.ppt` `CurrentUserAtom`. The LibreOffice fallback does (full re-render). |
| L8 | **exiftool ignore-list is hand-maintained** | `engines/exiftool.py`'s "structural tag" allow-list is still curated by hand; the golden corpus now guards the common cases but an exotic camera tag could slip through. |
| L10 | **Everything runs single-process, in-memory** | No parallelism for big trees; the API job registry is lost on restart. |

---

## Now — v0.3 plan (gap-closing sweep)

Ordered batches, each landing as its own commit:

1. ~~**Format coverage** — GIF (comment/XMP blocks); `.docm/.xlsm/.pptm` +
   `.dotx/.xltx/.potx` (OOXML engine already fits); ODF `Thumbnails/`.
   Extend `DEFAULT_FILETYPES`.~~ **Done.** GIF now scrubs (EXIF/XMP + the
   comment extension) and the `GIF` exiftool group is treated as
   structural so a scrubbed GIF no longer trips the exit-code gate; the
   JPEG/GIF `Comment` block is tracked as a real leak. Macro-enabled and
   template OOXML flow through the office engine — `vbaProject.bin` is
   kept but the report flags the file as partly scrubbed. ODF
   `Thumbnails/` preview + its manifest entry are dropped.
   `DEFAULT_FILETYPES` is 29 extensions. *(narrows L5, L6)*
2. ~~**XFA form data** — with `--strip-form-values`, blank the
   `/AcroForm/XFA` `datasets` packet (`<xfa:data>` contents).~~ **Done.**
   Every XFA packet (array form or a single `xdp:xdp` stream) has its
   `<xfa:data>` body blanked; the template, the datasets wrapper and its
   `<dd:dataDescription>` schema are kept. *(closes the XFA hole in L2's
   opt-in exception)*
3. ~~**`watch` hardening** — lockfile (one watcher per dir), `--pattern`
   glob filter, prune state entries for vanished files, `--jobs`
   pass-through.~~ **Done.** `.metascrub-watch.lock` (PID-stamped, steals
   a dead owner's lock); repeatable `--pattern GLOB`; `-j/--jobs N`
   (settled backlog scrubbed in one `clean_paths` call); vanished-file
   state entries pruned per scan.
4. ~~**Consistency + packaging** — `inspect --recurse/--media`; `py.typed`;
   `--exclude GLOB`; `--no-follow-symlinks`; `--progress` (rich bar);
   full `tool_versions()` (mutagen/olefile/soffice); `--debug` re-raise;
   `.editorconfig` / `CODEOWNERS` / issue+PR templates.~~ **Done.**
   `ruff format` was evaluated and **not** adopted: the codebase uses a
   deliberate hand-aligned style (grouped list literals, compact
   multi-arg calls) that `ruff format` flattens, and `ruff check` already
   gates correctness in CI. `.editorconfig` records the 120-col width.
5. ~~**Video EBML/RIFF** — a minimal `.mkv/.webm` EBML `Tags` stripper and
   `.avi` RIFF `LIST/INFO` + `IDIT` stripper (exiftool can't write
   these).~~ **Done.** `engines/ebml_riff.py` blanks the `Tags` block +
   `Info` title/date/app-name fields (Matroska) and `LIST INFO` + `IDIT`
   (AVI) in place, overwriting with `Void`/`JUNK` padding of identical
   length — deterministic, `--in-place`-safe, track data untouched.
   *(closes L7)*
6. ~~**More containers** — `.tar`/`.tar.gz` (stdlib), `.msg` (optional
   `extract-msg`), `.7z` (optional `py7zr`).~~ **Done.** `.tar` +
   `.tar.gz`/`.tgz`/`.tar.bz2`/`.tar.xz` (stdlib; also normalises the
   uid/gid/uname/mtime member headers), `.7z` (`metascrub[archive]`),
   `.msg` (`metascrub[msg]`, read-only — `inspect` only).
7. **Native drop apps** —
   - macOS: `osacompile` droplet `MetaScrub.app` (no Xcode) + the Quick Action.
   - Windows: a WinForms drag-drop `.ps1` GUI + `SendTo` shortcut +
     a `winget` manifest; context-menu entry already shipped.
   - Linux: a `.desktop` MIME handler + a `zenity` drop dialog + the
     Nautilus script.
8. **Web/API parity** — `--recurse` / `--media` on the web form and the
   API; a `GET /v1/formats` endpoint; refreshed screenshots.
9. **Ship pipeline** — `.github/workflows/docker.yml` builds and pushes
   `ghcr.io/gorkemguler/metascrub` on a tag; document the nginx/Caddy
   reverse-proxy recipe next to `--api-key`.

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

Shipped from this list: a `rich` progress bar (`clean --progress`), and
deeper video (EBML `Tags` for `.mkv/.webm`, RIFF `LIST`/`IDIT` for `.avi`).

Still open:
- A combined HTML report across runs; copy-as-CSV.
- Windows `IExplorerCommand` shell extension; `winget` / Homebrew /
  `.deb` packages; publish the GitHub Action to the Marketplace.

## Someday — bigger bets

- **Recursive containers** — done: `metascrub clean --recurse` descends
  into `.zip` / `.tar*` / `.7z` archives and `.eml` emails
  (`engines/container.py`), scrubs each member, repacks, depth-limited.
  `.msg` (Outlook) is inspect-only. Still open: a writable `.msg` path,
  and re-embedding scrubbed copies of a PDF's *own* `/EmbeddedFiles`.
- **Content-side flagging** — a `--flag-content` that runs MetaScout's
  `--scan-content` over the output and warns if PII still sits in the
  *body* text. For now the README just points at running `metascout
  local-scan --scan-content` as a second pass.
- **Deterministic rebuilds** — *done and guarded*: `tests/test_deterministic.py`
  asserts a second scrub of the same file with the same options is
  byte-identical (every format bar `--strip-pdf-id`, which is random by
  design).
