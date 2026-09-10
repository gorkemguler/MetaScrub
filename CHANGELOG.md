# Changelog

All notable changes to MetaScrub. Dates are ISO. This project aims to
follow [Semantic Versioning](https://semver.org/) once it hits 1.0.

## [Unreleased]

### Added
- **`metascrub watch` hardening**: a PID-stamped `.metascrub-watch.lock`
  keeps a second watcher off the same directory (a lock held by a dead
  process is stolen); `--pattern GLOB` (repeatable) filters what's picked
  up; `-j/--jobs N` scrubs a settled backlog through the thread pool in
  one pass; state entries for files that have since vanished are pruned
  each scan so `.metascrub-watch.json` can't grow without bound.
- **PDF XFA forms**: `--strip-form-values` now also blanks the
  `<xfa:data>` subtree of every `/AcroForm/XFA` packet (array form or a
  single `xdp:xdp` stream) — that's the data typed into an XFA form. The
  XFA template (form definition), the `datasets` wrapper and its
  `<dd:dataDescription>` schema are kept, and `NeedAppearances` is set.
- **Format coverage**: macro-enabled Office (`.docm .xlsm .pptm`) and
  template (`.dotx .dotm .xltx .xltm .potx .potm`) files now scrub through
  the OOXML engine; `vbaProject.bin` is kept but the report flags the file
  as only partly scrubbed. GIF (`.gif`) images: EXIF/XMP and the comment
  extension. ODF `Thumbnails/` preview image is dropped and its
  `META-INF/manifest.xml` entry pruned. `DEFAULT_FILETYPES` extended
  accordingly (29 extensions picked up when scanning a directory).

### Fixed
- Image probe/verify counted every `GIF`-group structural tag (version,
  screen geometry, colour-map, bit depth) as residual metadata, so every
  GIF tripped the CI exit-code gate. The `GIF` group is now recognised as
  structural; the JPEG/GIF `Comment` block is now tracked as a real leak
  (it had been filtered out with the rest of the `File` group).

## [0.2.0] — 2026-09-10

### Added
- **PDF**: annotation authors + timestamps (`/T` `/M` `/CreationDate`),
  embedded-file description + timestamps, `--password` for encrypted PDFs
  (the cleaned copy is written unencrypted), `--strip-pdf-id` (random
  trailer `/ID` per run), and opt-in `--strip-form-values` (blank AcroForm
  `/V` `/DV` + drop the cached `/AP`).
- **Legacy Office** `.doc/.xls/.ppt`: a pure-Python, in-place OLE2
  property-stream scrubber (`engines/ole2.py`). Keeps the original format,
  works with `--in-place`. LibreOffice (`soffice`) is now only a fallback
  for an unparseable container.
- **SVG** engine: strips `<metadata>`, `sodipodi:` / `inkscape:` /
  Adobe-Illustrator elements and attributes, and editor comments.
- **Office**: opt-in `--strip-office-authors` — blanks tracked-change /
  comment author names + dates across Word / PowerPoint / Excel; the text
  is kept.
- `metascrub diff <runA> <runB>` — compare two run reports; exit 1 when a
  file regained metadata.
- `--backup` — keep `<name>.orig` next to an `--in-place` scrub.
- Golden-corpus test (`tests/test_corpus.py`), `ruff` + `mypy` config, a
  GitHub Actions CI matrix, and a `slow` pytest marker.
- **REST API**: `--api-key` (env `METASCRUB_API_KEY`) on every `/v1` route
  except `/v1/health`; streaming uploads with `--max-upload-mb` /
  `--max-files` caps; a SQLite-backed job registry so status survives a
  restart (`--run-ttl-days` prunes old runs); `--log-json` access log.
  `metascrub api` / `web` refuse a non-loopback bind without auth unless
  `--insecure`.
- **Docker**: non-root user, `HEALTHCHECK`.
- `--jobs N` (parallel scrub), `--quarantine DIR` (dated recoverable
  originals), `--policy publish|internal|minimal`, and a `.metascrub.toml`
  project config.
- `metascrub watch <dir>` — scrub an FTP/SFTP drop folder on a poll loop.
- **Audio/video**: `--media` scans `.mp3/.m4a/.flac/.ogg/.opus/.wav/.aiff`
  (tags + cover art via `mutagen`, `metascrub[media]`) and
  `.mp4/.mov/.m4v/.mkv/.webm` (metadata atoms via exiftool, track kept).
  HEIC via `pillow-heif` in the Pillow fallback.
- **Containers**: `--recurse` descends into `.zip` archives and `.eml`
  emails, scrubbing each member/attachment with its own engine (depth-limited).
- `metascrub clean --check` (exit 3 on metadata), `.pre-commit-hooks.yaml`,
  `action.yml` GitHub Action, and right-click installers in `platform/`.

### Fixed
- ODF `probe` looked for `<meta>` in the wrong XML namespace, so
  `inspect` / dry-run / verify were blind to `.odt/.ods` metadata (the
  scrub itself was unaffected).
- Web UI: a run under a symlinked `--output-dir` (e.g. `/tmp` on macOS)
  404'd on every `/report`, `/zip`, `/file` — the traversal guard now
  compares realpaths on both sides.

## [0.1.0] — 2026-09-09

Initial release: CLI (`clean`, `inspect`), local Flask web UI, job-based
FastAPI service. PDF (pikepdf), Office/ODF (stdlib zipfile) and image
(exiftool) engines. Copy-by-default with `--in-place`, a verify re-scan,
and JSON + HTML before/after reports.
