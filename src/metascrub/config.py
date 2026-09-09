from __future__ import annotations

from dataclasses import dataclass, field

# Extensions MetaScrub will pick up when pointed at a directory. Mirrors
# MetaScout's DEFAULT_FILETYPES (so the two tools agree on what a
# "document" is) plus the raster image formats MetaScrub can also scrub.
DEFAULT_FILETYPES = [
    "pdf",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "odt", "ods", "odp",
    "jpg", "jpeg", "png", "tif", "tiff", "heic", "webp",
]

# OOXML containers the office engine rewrites in full (pure zipfile, no
# external dependency).
OOXML_EXTENSIONS = frozenset({"docx", "xlsx", "pptx"})
# OpenDocument containers — same zip treatment, different metadata member.
ODF_EXTENSIONS = frozenset({"odt", "ods", "odp"})
# Legacy OLE2 / Compound File Binary formats. No safe stdlib-only strip
# exists for these, so v1 reports them as "unsupported" rather than
# pretending to clean them. Convert to the modern format first, or wait
# for the LibreOffice-headless path in a later version.
LEGACY_OFFICE_EXTENSIONS = frozenset({"doc", "xls", "ppt"})

IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "tif", "tiff", "heic", "webp"})
PDF_EXTENSIONS = frozenset({"pdf"})


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
    output_dir: str = "./metascrub_cleaned"

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

    def wants_field(self, name: str) -> bool:
        """True if `name` should be preserved rather than stripped."""
        lowered = name.strip().lower()
        return any(lowered == k.strip().lower() for k in self.keep_fields)
