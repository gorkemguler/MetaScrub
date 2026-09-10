<p align="center">
  <img src="assets/banner.svg" alt="MetaScrub" width="100%">
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-2dd4a7.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-2dd4a7.svg">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-7dd88f.svg">
  <img alt="Status" src="https://img.shields.io/badge/status-active%20development-f6c454.svg">
</p>

<p align="center">
  Bulk metadata scrubbing for PDF, Office and image files.<br>
  Strip the metadata, keep the document — with a before/after proof report.
</p>

<p align="center">
  <sub>Pairs with <a href="https://github.com/gorkemguler/MetaScout">MetaScout</a>: MetaScout <i>finds</i> the leaks, MetaScrub <i>fixes</i> them.</sub>
</p>

<p align="center"><sub>🇬🇧 English · <a href="README.tr.md">🇹🇷 Türkçe</a></sub></p>

<p align="center">
  <img src="assets/screenshot-report.png" alt="MetaScrub before/after report — 3 files, 18 metadata fields removed, 0 residual" width="90%">
</p>

---

## What is this?

An organisation runs MetaScout against its own site and finds a pile of published PDFs and
Office documents leaking author names, internal file paths, software/OS fingerprints and GPS
coordinates. Now someone has to actually **clean those files**. That's MetaScrub.

Point it at a folder (or drag files into the web UI, or POST them to the API) and it:

1. **scans** every supported file for embedded metadata,
2. **strips** it — aggressively by default — writing cleaned copies (originals untouched) or
   overwriting in place,
3. **verifies** each cleaned file by re-scanning it, and
4. **reports** exactly what was removed, per file, as JSON and a styled HTML page you can hand
   to a security team as evidence.

It only touches **metadata** — the document's visible content (body text, images, a scanned
signature) is never modified.

## What it removes

| Format | Engine | Removed |
| --- | --- | --- |
| **PDF** | [pikepdf](https://github.com/pikepdf/pikepdf) (QPDF) | `/Info` dictionary (Author, Title, Producer, Creator, CreationDate, …), the XMP metadata packet, `/PieceInfo` and other application-private data, page-level metadata, annotation authors + timestamps (`/T` `/M` `/CreationDate`), and the description + timestamps on embedded-file attachments. The file is **fully rewritten**, so values sitting in superseded cross-reference sections can't be recovered from the output. Encrypted PDFs need `--password`. With `--strip-form-values`: AcroForm field values and the XFA `<xfa:data>` packet too. |
| **Office** `.docx .xlsx .pptx` (+ macro-enabled `.docm .xlsm .pptm` and templates `.dotx .dotm .xltx .xltm .potx .potm`) | stdlib `zipfile` | `docProps/core.xml` (creator, lastModifiedBy, revision, timestamps), `docProps/app.xml` (Company, Manager, Template path), `docProps/custom.xml`, the embedded thumbnail, and Word revision-save-id fingerprints (`w:rsids`) from `settings.xml`. Dangling relationships and content-type overrides are pruned; per-member zip timestamps are normalised. `vbaProject.bin` is **kept** (breaking macros is worse than the small chance a name hides in it) and the report flags that the file was only partly scrubbed. |
| **OpenDocument** `.odt .ods .odp` | stdlib `zipfile` | `meta.xml` — initial-creator, creator, generator, editing-cycles/duration, timestamps, document statistics, user-defined fields — plus the `Thumbnails/` preview image (a rendered snapshot of the first page) and its `META-INF/manifest.xml` entry. |
| **Legacy Office** `.doc .xls .ppt` | `olefile` (pure Python) | The `\x05SummaryInformation` / `\x05DocumentSummaryInformation` property streams — author, last-saved-by, company, manager, template, title, timestamps, custom properties — are patched out **in place**: same file size, same format, same structure. `--in-place` works. If a container can't be parsed, MetaScrub falls back to a LibreOffice (`soffice`) re-render to `.docx/.xlsx/.pptx`. |
| **SVG** `.svg` | stdlib `xml` | `<metadata>` (RDF/Dublin-Core author/title/licence), `sodipodi:` / `inkscape:` / Adobe-Illustrator elements and attributes, and editor comments (`<!-- Created with … -->`). The drawing itself is untouched. |
| **Images** `.jpg .jpeg .png .gif .tif .tiff .heic .heif .webp` | [ExifTool](https://exiftool.org) | All EXIF / IPTC / XMP / GPS / MakerNotes, PNG/WebP text chunks and the JPEG/GIF comment block. The ICC colour profile and EXIF orientation are kept by default so the picture still renders correctly (`--no-keep-color-profile` / `--no-keep-orientation` to drop those too). HEIC also works via `pillow-heif` when exiftool is absent. |
| **Audio / video** `.mp3 .m4a .flac .ogg .opus .wav .aiff` / `.mp4 .mov .m4v .3gp .mkv .webm .avi` | `mutagen` / ExifTool / pure Python | Audio: all tags (ID3 / Vorbis / iTunes) and embedded cover art — `pip install 'metascrub[media]'`. MP4-family video: exiftool clears the metadata atoms (`ItemList`, `Keys`, `UserData`, XMP — artist, `Make`/`Model` from a phone, GPS, `CreationDate`). **Matroska / WebM / AVI** (exiftool can't write these): the whole EBML `Tags` block and the `Info` title / dates / muxer-and-writer app names are blanked in place — overwritten with `Void` / `JUNK` padding of identical length, so the file length is unchanged and `--in-place` works; the track data is never touched. Not scanned by default — pass **`--media`** (or list the extensions in `--filetypes`). Spot-check playback. |
| **Containers** `.zip .eml .tar .tar.gz .tgz .tar.bz2 .tar.xz .7z .msg` | stdlib `zipfile` / `tarfile` / `email`; `py7zr` / `extract-msg` (optional) | With **`--recurse`**: each supported member of an archive, and each email attachment, is scrubbed with its own engine and the archive/message repacked. `.tar*` also has its per-member uid/gid/username/mtime headers normalised (a leak of the packer's identity). `.7z` needs `pip install 'metascrub[archive]'`. `.msg` (Outlook) is **read-only** — `metascrub inspect --recurse` lists what's inside (needs `metascrub[msg]`); export to `.eml` to scrub. Non-scrubbable members pass through untouched. Nesting is followed (depth-limited). |

`--keep Title` (repeatable) spares a named field from the otherwise-aggressive strip.
`--backup` keeps `<name>.orig` next to an `--in-place` scrub.

Two **opt-in** flags go past metadata into identity data that's technically content:
`--strip-form-values` blanks PDF form values — AcroForm fields (`/V` `/DV`) and their cached
appearance, plus the `<xfa:data>` packet of an XFA form (the XFA template and schema are kept);
`--strip-office-authors` blanks Office tracked-change / comment **author names and dates**
(the change and comment text stays, so accept/reject still works).

## Install

```bash
pip install metascrub                     # core: PDF + Office scrubbing
pip install 'metascrub[api]'              # + the REST API service
pip install 'metascrub[media]'            # + audio tag scrubbing (mutagen)
pip install 'metascrub[archive]'          # + .7z recursion (py7zr)
pip install 'metascrub[msg]'              # + read-only .msg inspection (extract-msg)
pip install 'metascrub[image-fallback]'   # + Pillow (weak image fallback if exiftool is absent)
```

Image scrubbing needs the **exiftool** binary on `PATH`:

```bash
brew install exiftool                        # macOS
sudo apt install libimage-exiftool-perl      # Debian / Ubuntu
```

PDF, Office (modern **and** legacy `.doc/.xls/.ppt`), ODF and SVG scrubbing are pure Python
and need nothing extra. **LibreOffice** (`soffice`) is only used as a fallback for a legacy
container the in-place patcher can't parse.

> Python 3.10+ is supported. On a brand-new Python where `pikepdf` has no wheel yet, install
> under 3.12 instead.

## CLI

<p align="center">
  <img src="assets/screenshot-cli.svg" alt="metascrub inspect and metascrub clean in a terminal" width="90%">
</p>

### Inspect — see what's in the files (read-only)

```bash
metascrub inspect ./published-docs
metascrub inspect leak.pdf report.docx --json
```

Run this on the files MetaScout flagged to see exactly what they carry before you scrub.

### Clean

```bash
# default: originals untouched, cleaned copies written under ./metascrub_cleaned/,
# mirroring the input tree, plus report.json + report.html
metascrub clean ./published-docs

# overwrite the originals instead (asks first; -y to skip the prompt)
metascrub clean ./published-docs --in-place

# preview only, change nothing
metascrub clean ./published-docs --dry-run

# keep document titles, Turkish report
metascrub clean ./published-docs --keep Title --report-lang tr

# just some files
metascrub clean a.pdf b.docx c.jpg --out ./clean
```

Useful flags: `--filetypes`, `--no-recursive`, `--out DIR`, `--keep FIELD`, `--dry-run`,
`--no-verify`, `--no-keep-color-profile`, `--no-keep-orientation`, `--report-lang en|tr`,
`--password` (encrypted PDFs), `--strip-pdf-id`, `--backup` (keep `<name>.orig` with `--in-place`),
`--strip-form-values`, `--strip-office-authors` (opt-in — see above),
`--jobs N` (scrub N files in parallel), `--quarantine DIR` (overwrite the original but move
it to `DIR/<date>/` first — recoverable, safer than `--in-place`),
`--policy publish|internal|minimal` (named presets),
`--exclude GLOB` (repeatable — skip files/dirs when walking),
`--no-follow-symlinks` (don't scrub a symlinked file), `--progress` (a progress bar), and the
group-level `metascrub --debug …` (re-raise on the first failing file instead of recording it).

`metascrub inspect` takes `--media` and `--recurse` too, so you can point it at an archive or a
video and see what's inside before scrubbing.

**Project config:** a `.metascrub.toml` in the working directory or a parent (up to the git
root) sets defaults per command — CLI flags and env vars still win.

```toml
[clean]
strip-office-authors = true
jobs = 4
keep = ["Title"]
```

**Exit codes** (so it works as a CI gate): `0` clean · `1` a file errored · `2` a cleaned file
still carried metadata on the verify re-scan · `3` (`--check` only) metadata found.

### Diff — track a directory over time

```bash
metascrub clean ./published --out ./scan-jan     # once a month, into dated dirs
metascrub clean ./published --out ./scan-feb
metascrub diff ./scan-jan ./scan-feb             # what changed?
```

Shows files added/removed between the two runs and, the useful part, files where metadata
**reappeared** (someone re-saved the document in an editor). Exit code `1` if anything
regained metadata — drop it in a cron job.

### Watch — keep a drop folder scrubbed

```bash
metascrub watch /srv/ftp/incoming --move-processed /srv/ftp/scrubbed --interval 10 --settle 5
metascrub watch ./inbox --once                       # one pass, for cron
metascrub watch ./inbox --pattern 'invoice-*.pdf' -j 4   # filter + parallel backlog
```

A poll loop for an FTP/SFTP landing zone: a file is only touched once it has stopped
changing for `--settle` seconds (a half-finished upload is never scrubbed), state lives in
`<dir>/.metascrub-watch.json` so a restart doesn't reprocess everything, and a file
re-dropped with a newer timestamp is handled again. A `.metascrub-watch.lock` file keeps a
second watcher off the same directory (a lock left by a dead process is stolen).
`--pattern GLOB` (repeatable) narrows what's picked up; `-j/--jobs N` scrubs a backlog in
parallel; state entries for files that have since vanished are pruned each pass. Scrubs in
place by default; `--to DIR` writes cleaned copies instead. A systemd template unit is in
[`platform/linux/`](platform/linux/metascrub-watch@.service).

## Web UI

```bash
metascrub web           # opens http://127.0.0.1:8770/
```

Drag files onto the page, get them back scrubbed — individually or as a zip — with a
per-file before/after view and the full report. Past runs are listed under **History**.
Local, single-user, **no authentication** — don't expose it to a network.

<p align="center">
  <img src="assets/screenshot-web.png" alt="MetaScrub local web UI — drag-and-drop file drop zone" width="90%">
</p>

## REST API

For a Linux server, an FTP drop-box, or a CI pipeline that needs to hand files off to be
cleaned:

```bash
pip install 'metascrub[api]'
metascrub api           # http://127.0.0.1:8000/  ·  interactive docs at /docs
```

```bash
# submit
curl -sS -X POST http://127.0.0.1:8000/v1/clean \
  -F files=@leak.pdf -F files=@report.docx -F report_lang=en
# -> {"job_id": "...", "links": {...}}

# poll
curl -sS http://127.0.0.1:8000/v1/clean/<job_id>

# pull the cleaned files + report as a zip
curl -sSL -o cleaned.zip http://127.0.0.1:8000/v1/clean/<job_id>/download
```

Jobs run in a bounded background thread pool; `--max-workers` / `--max-pending` size it.
Uploads stream to disk with `--max-upload-mb` / `--max-files` caps.

**Auth:** `metascrub api --api-key KEY` (or `METASCRUB_API_KEY`) requires that key on every
`/v1` route except `/v1/health` — send it as `X-API-Key: KEY` or `Authorization: Bearer KEY`.
Both `api` and `web` **refuse to bind a non-loopback host** (`0.0.0.0`, a LAN IP) with no
auth unless you pass `--insecure`; put a reverse proxy in front, or key the API, or stay on
`127.0.0.1`.

```bash
metascrub api --host 0.0.0.0 --api-key "$(openssl rand -hex 24)"
curl -H "X-API-Key: $KEY" -F files=@leak.pdf http://server:8000/v1/clean
```

## Docker

```bash
docker build -t metascrub .

# web UI
docker run --rm -p 127.0.0.1:8770:8770 -v "$(pwd)/metascrub_cleaned:/data" metascrub

# REST API
docker run --rm -p 127.0.0.1:8000:8000 -v "$(pwd)/metascrub_cleaned:/data" metascrub \
  api --host 0.0.0.0 --port 8000 --output-dir /data

# one-off: scrub a mounted folder
docker run --rm -v "$(pwd)/docs:/work" metascrub clean /work --out /work/cleaned
```

Or `docker compose up --build` (web UI); `docker compose --profile api up metascrub-api` (API).

## How thorough is it?

- **PDF** — a full QPDF rewrite, not an incremental update, so the removed `/Info` and XMP
  aren't left behind in an old xref section. Annotation authors/dates and embedded-file
  metadata go too; the annotation's visible text and the attached file itself stay.
  **Signed PDFs are skipped, not broken** — scrubbing would invalidate the signature;
  re-export an unsigned copy if you need it cleaned. **Encrypted PDFs** without `--password`
  are skipped; with it, the cleaned copy is written unencrypted (the result says so).
- **Office / ODF** — the metadata parts are deleted from the package (or, for ODF, emptied),
  not merely blanked, and the references to them are pruned so nothing dangles.
- **Images** — `exiftool -all=`, which is the reference tool for this.
- **`--verify`** (on by default) re-scans every cleaned file and lists anything still present
  in the report; the CLI exits `2` if so.
- **Deterministic** — scrubbing the same file twice with the same options gives byte-identical
  output (checked in CI), so a scrub is auditable. `--strip-pdf-id` is the deliberate exception.

### Limitations

- Content is out of scope by design: text in the document body, a visible/scanned signature,
  text baked into an image — MetaScrub won't touch those. (MetaScout's `--scan-content` finds
  them; removing them is a manual edit.)
- Legacy `.doc / .xls / .ppt` are not scrubbed (convert first).
- Not a certified sanitisation tool. Verify anything high-stakes yourself — that's what
  `metascrub inspect` on the output, or a second pass with MetaScout, is for.

## Desktop integration

All in **[`platform/`](platform/)**, one install command each — everything scrubs in place:

- **macOS** — a drag-and-drop `MetaScrub.app` (built with `osacompile`, no Xcode), plus a
  Finder **Quick Action**.
- **Windows** — a WinForms **drop window**, a **Send to** menu entry, an Explorer
  **right-click** entry, and a `winget` manifest (template).
- **Linux** — a `.desktop` launcher / *Open With* handler (with a `zenity` picker), a
  Nautilus/Nemo/Caja **script**, and a `systemd` **watch** unit.

## CI / hooks

`metascrub clean --check` implies `--dry-run` and exits **3** if any file still carries
metadata (0 if clean, 1 on error) — a gate for pre-commit and CI.

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/gorkemguler/MetaScrub
  rev: main
  hooks: [{ id: metascrub }]
```

```yaml
# .github/workflows/no-metadata.yml
- uses: gorkemguler/MetaScrub@main
  with:
    paths: docs/ public/
    mode: check        # or "fix" to scrub in place and commit
```

## Roadmap

See **[ROADMAP.md](ROADMAP.md)** for what's shipped, the known limitations, and the backlog
(inotify watch, SFTP mode, `--jobs`, `--quarantine`, `.metascrub.toml`, policy profiles,
audio/video, PyPI, recursive-container scrubbing).

## License

MIT — see [LICENSE](LICENSE).
