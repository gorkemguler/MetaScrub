# Changelog

All notable changes to MetaScrub. Dates are ISO. This project aims to
follow [Semantic Versioning](https://semver.org/) once it hits 1.0.

## [Unreleased]

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
