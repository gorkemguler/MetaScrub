from __future__ import annotations

import json
import os
import shutil
import subprocess

# Group1 names and bare tags that are never a metadata leak: they describe
# the file's own container/pixels, not who made it or where — and most of
# them legitimately survive an aggressive `-all=` strip (JFIF APP0, the
# kept ICC profile, the kept Orientation), so counting them as "residual"
# would be a false alarm. Filtered out of probe() on both sides.
_STRUCTURAL_GROUPS = {
    "ExifTool", "File", "System", "Composite", "JFIF",
    "ICC_Profile", "ICC-header", "ICC-view", "ICC-meas", "ICC-chrm", "PrintIM",
}
_STRUCTURAL_TAGS = {
    # geometry / encoding — intrinsic to the pixels
    "ImageWidth", "ImageHeight", "ImageSize", "Megapixels", "BitDepth",
    "ColorType", "Compression", "Filter", "Interlace", "BitsPerSample",
    "ColorComponents", "YCbCrSubSampling", "YCbCrPositioning", "EncodingProcess",
    "JFIFVersion", "ExifByteOrder", "PixelUnits", "PixelsPerUnitX", "PixelsPerUnitY",
    "ImageDataMD5", "CurrentIPTCDigest", "Gamma", "SRGBRendering", "BackgroundColor",
    "Primaries", "WhitePoint",
    # version / colour-model markers exiftool re-emits for a valid file
    "ExifVersion", "FlashpixVersion", "ComponentsConfiguration", "ColorSpace",
    "GPSVersionID",
    # kept on purpose (see CleanConfig.keep_orientation / keep_color_profile)
    "Orientation", "ResolutionUnit", "XResolution", "YResolution",
    "ProfileCMMType", "ProfileVersion", "ProfileClass", "ColorSpaceData",
    "ProfileConnectionSpace", "ProfileDescription", "ProfileCreator",
}


def exiftool_available() -> bool:
    return shutil.which("exiftool") is not None


def exiftool_version() -> str | None:
    if not exiftool_available():
        return None
    try:
        out = subprocess.run(["exiftool", "-ver"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def read_tags(path: str, *, timeout: int = 30) -> dict[str, str]:
    """Return {"<Group1>:<Tag>": "<value>"} for every metadata tag in
    `path`, minus purely structural ones. Empty dict on any failure.
    """
    cmd = ["exiftool", "-j", "-a", "-G1", "-s", "-n", "-api", "largefilesupport=1", path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return {}
    if not proc.stdout:
        return {}
    try:
        records = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    if not records:
        return {}
    record = records[0]
    tags: dict[str, str] = {}
    for key, value in record.items():
        if key == "SourceFile":
            continue
        group, _, tag = key.partition(":")
        if not tag:
            group, tag = "", key
        if group in _STRUCTURAL_GROUPS or tag in _STRUCTURAL_TAGS:
            continue
        tags[key] = _stringify(value)
    return tags


def strip_all(
    src: str,
    dst: str,
    *,
    keep_color_profile: bool = True,
    keep_orientation: bool = True,
    keep_tags: list[str] | None = None,
    timeout: int = 60,
) -> tuple[bool, str]:
    """Write a metadata-free copy of `src` to `dst` with exiftool.

    Works on a copy so the mutating exiftool call never sees `src`: copy
    src -> dst, then `-all=` wipes EXIF/IPTC/XMP/GPS/MakerNotes and
    PNG/WebP text chunks in dst, and a trailing `-tagsFromFile <src>`
    clause copies back only the handful of tags we deliberately keep.

    Returns (ok, message).
    """
    preserved: list[str] = []
    if keep_color_profile:
        preserved.append("-ICC_Profile")
    if keep_orientation:
        preserved.append("-Orientation")
    for t in keep_tags or []:
        preserved.append(f"-{t}")

    try:
        shutil.copyfile(src, dst)
    except OSError as exc:
        return False, f"could not stage output file: {exc}"

    cmd = ["exiftool", "-all=", "-overwrite_original"]
    if preserved:
        cmd += ["-tagsFromFile", src, *preserved]
    cmd += [dst]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        _rm(dst)
        return False, f"exiftool timed out after {timeout}s"
    except OSError as exc:
        _rm(dst)
        return False, f"exiftool could not run: {exc}"

    msg = (proc.stdout + proc.stderr).strip()
    # exiftool exits 0 and prints "1 image files updated" on success; on a
    # format it can't write it exits non-zero with an explanatory stderr.
    if proc.returncode != 0:
        _rm(dst)
        return False, msg or f"exiftool exited {proc.returncode}"
    return True, msg


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# Video metadata atoms/groups that are safe to clear without touching the
# track structure (so the file stays playable and correctly rotated).
_VIDEO_CLEAR = [
    "-QuickTime:ItemList:all=", "-QuickTime:Keys:all=", "-QuickTime:UserData:all=",
    "-XMP:all=", "-ID3:all=", "-RIFF:all=", "-Matroska:all=",
    "-Encoder=", "-HandlerDescription=", "-Comment=", "-Title=", "-Artist=",
    "-CreationDate=", "-ContentCreateDate=",
]


def strip_media(src: str, dst: str, *, is_video: bool, timeout: int = 120) -> tuple[bool, str]:
    """Scrub an audio or video file. Audio: `-all=` (tags only, structure
    is untouched by exiftool for audio). Video: clear the metadata atoms
    but leave the track headers alone."""
    try:
        shutil.copyfile(src, dst)
    except OSError as exc:
        return False, f"could not stage output file: {exc}"

    cmd = ["exiftool", "-m", "-overwrite_original"]
    cmd += _VIDEO_CLEAR if is_video else ["-all="]
    cmd += [dst]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        _rm(dst)
        return False, f"exiftool timed out after {timeout}s"
    except OSError as exc:
        _rm(dst)
        return False, f"exiftool could not run: {exc}"
    msg = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        _rm(dst)
        return False, msg or f"exiftool exited {proc.returncode}"
    return True, msg


def _stringify(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
