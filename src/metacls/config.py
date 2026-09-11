from __future__ import annotations

from dataclasses import dataclass, field

# Extensions MetaCLS will pick up when pointed at a directory. Mirrors
# MetaScout's DEFAULT_FILETYPES (so the two tools agree on what a
# "document" is) plus the raster image formats MetaCLS can also scrub.
DEFAULT_FILETYPES = [
    "pdf",
    "doc", "docx", "docm", "dotx", "dotm",
    "xls", "xlsx", "xlsm", "xltx", "xltm",
    "ppt", "pptx", "pptm", "potx", "potm",
    "odt", "ods", "odp",
    "svg",
    "jpg", "jpeg", "png", "gif", "tif", "tiff", "heic", "heif", "webp",
]

# OOXML containers the office engine rewrites in full (pure zipfile, no
# external dependency) — the document, macro-enabled and template
# variants all share the docProps/* layout.
OOXML_EXTENSIONS = frozenset({
    "docx", "docm", "dotx", "dotm",
    "xlsx", "xlsm", "xltx", "xltm",
    "pptx", "pptm", "potx", "potm",
})
# OpenDocument containers — same zip treatment, different metadata member.
ODF_EXTENSIONS = frozenset({"odt", "ods", "odp"})
# Legacy OLE2 / Compound File Binary formats. No safe stdlib-only strip
# exists for these, so v1 reports them as "unsupported" rather than
# pretending to clean them. Convert to the modern format first, or wait
# for the LibreOffice-headless path in a later version.
LEGACY_OFFICE_EXTENSIONS = frozenset({"doc", "xls", "ppt"})

IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "gif", "tif", "tiff", "heic", "heif", "webp"})
PDF_EXTENSIONS = frozenset({"pdf"})
SVG_EXTENSIONS = frozenset({"svg"})

# Audio + video. Not in DEFAULT_FILETYPES — added by `metacls clean
# --media` or an explicit --filetypes. Handled with exiftool: audio tags
# strip cleanly; for video only the metadata atoms are cleared, the track
# structure (incl. the rotation matrix) is left alone.
AUDIO_EXTENSIONS = frozenset({"mp3", "m4a", "aac", "flac", "wav", "ogg", "opus", "wma", "aiff", "aif"})
VIDEO_EXTENSIONS = frozenset({"mp4", "m4v", "mov", "mkv", "webm", "avi", "3gp"})
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

# Containers whose members are themselves scrubbable — descended into with
# `metacls clean --recurse`. Not in DEFAULT_FILETYPES.
#   zip / eml           — stdlib
#   tar + compressed    — stdlib tarfile (auto-detects gz/bz2/xz); bare
#                         gz/bz2/xz only route here when they are a tar
#   7z                  — optional py7zr  (metacls[archive])
#   msg (Outlook)       — optional extract-msg, read-only (probe only)
CONTAINER_EXTENSIONS = frozenset({
    "zip", "eml",
    "tar", "tgz", "tbz2", "tbz", "txz", "gz", "bz2", "xz",
    "7z", "msg",
})


# Named bundles of `metacls clean` settings. Explicit flags still win;
# `--policy` only shifts the defaults.
POLICIES: dict[str, dict] = {
    # Everything, for a file about to go public.
    "publish": {"strip_form_values": True, "strip_office_authors": True, "strip_pdf_id": True},
    # Standard scrub, but keep document titles so files stay findable
    # inside the org.
    "internal": {"keep_fields": ("Title",)},
    # Only the always-on metadata strip — no opt-in extras (the default).
    "minimal": {},
}


@dataclass
class CleanConfig:
    """Everything that controls a scrub run. Shared verbatim by the CLI,
    the local web UI and the REST API so their behaviour can't drift.
    """

    filetypes: list[str] = field(default_factory=lambda: list(DEFAULT_FILETYPES))
    recursive: bool = True

    # False (default): originals are never touched; a cleaned copy is
    # written under output_dir, mirroring the input tree. True: clean into
    # a temp file, then os.replace over the original — irreversible, so the
    # CLI confirms first unless --yes is given.
    in_place: bool = False
    output_dir: str = "./metacls_cleaned"

    # Metadata field names to spare from the otherwise-aggressive strip,
    # e.g. ["Title"]. Matched case-insensitively against the leaf field
    # name (DocInfo key, XMP/OOXML local name, EXIF tag).
    keep_fields: list[str] = field(default_factory=list)

    # Only probe and report what's there; write nothing.
    dry_run: bool = False

    # Re-probe every cleaned file and record whatever metadata is still
    # present in CleanResult.residual (drives the CLI's exit-code-2 gate).
    verify: bool = True

    # Image engine: keep the ICC colour profile and EXIF Orientation so a
    # scrubbed photo still renders with the right colours and rotation.
    keep_color_profile: bool = True
    keep_orientation: bool = True

    # Allow a cleaned copy to overwrite an existing file at the output path.
    overwrite: bool = False

    # PDF: password to open an encrypted document. Without it an encrypted
    # PDF is skipped (probe/inspect just reports "<encrypted>").
    pdf_password: str | None = None

    # PDF: don't carry a deterministic /ID forward — write a fresh random
    # one on every scrub, so two scrubbed copies of the same file can't be
    # correlated by their document identifier either.
    strip_pdf_id: bool = False

    # --in-place only: keep the untouched original next to the scrubbed
    # file as "<name>.orig" (never overwrites an existing .orig).
    backup: bool = False

    # Like --in-place, but the original is moved into
    # <quarantine>/<YYYY-MM-DD>/<relpath> first — recoverable, out of the
    # way. Takes precedence over in_place / output_dir when set.
    quarantine: str | None = None

    # Files scrubbed in parallel (thread pool). 1 = sequential.
    jobs: int = 1

    # Descend into .zip / .eml and scrub each member. Depth-limited.
    recurse: bool = False
    _recurse_depth: int = 0  # internal — guards against zip bombs / loops

    # Directory-walk filters (no effect on paths named directly on the
    # command line — those are always honoured).
    #   exclude          — glob patterns; a file is skipped, and a
    #                      directory not descended, when its name or its
    #                      path relative to the walk root matches any.
    #   follow_symlinks  — False: don't scrub a symlinked file found in a
    #                      walk (writing through it would escape the tree).
    exclude: list[str] = field(default_factory=list)
    follow_symlinks: bool = True

    # Re-raise the underlying exception instead of turning one bad file
    # into a caught `error` result — for `--debug`.
    debug: bool = False

    # Aggressive, opt-in: also blank things that are arguably *content*
    # but are, in practice, a PII leak.
    #   strip_form_values   — PDF AcroForm field values (/V, /DV): the
    #                         name/address/etc. someone typed into a form.
    #   strip_office_authors — Office tracked-change and comment author
    #                         names/dates (the change/comment text stays).
    strip_form_values: bool = False
    strip_office_authors: bool = False

    def wants_field(self, name: str) -> bool:
        """True if `name` should be preserved rather than stripped."""
        lowered = name.strip().lower()
        return any(lowered == k.strip().lower() for k in self.keep_fields)
