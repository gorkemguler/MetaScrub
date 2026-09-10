# Contributing to MetaScrub

Thanks for helping. MetaScrub is small and has no heavy dependencies on
purpose — please keep it that way.

## Setup

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                 # full suite (needs exiftool; LibreOffice for the .doc fallback test)
pytest -q -m "not slow"   # fast suite (no external tools)
ruff check src tests
mypy src
```

## Ground rules

- **Metadata, not content.** MetaScrub removes *who / when / with what* —
  not the document's body, a comment's text, or pixels. Anything that
  crosses that line is opt-in behind an explicit flag (`--strip-form-values`,
  `--strip-office-authors`) and must be documented as such.
- **Never modify the source file** in an engine's `strip()` — write to
  `dst`. In-place is handled by `cleaner.py` (temp file + `os.replace`).
- **Every engine change needs a golden-corpus entry or a targeted test**
  proving `probe()` sees the metadata before and `[]` after.
- New format? Add an engine under `src/metascrub/engines/`, register it in
  `engines/__init__.py`, add its extensions to `config.DEFAULT_FILETYPES`,
  and a `tests/test_corpus.py` case.
- Keep the dependency list short. A new runtime dependency needs a reason
  in the PR description; prefer the stdlib.

## Commit / PR

- One logical change per PR. Update `CHANGELOG.md` under *Unreleased* and
  the relevant `ROADMAP.md` / `ROADMAP.tr.md` line.
- Keep the two READMEs in sync (English is source of truth).
