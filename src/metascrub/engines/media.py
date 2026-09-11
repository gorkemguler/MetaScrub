from __future__ import annotations

import os
import shutil

from ..config import AUDIO_EXTENSIONS, MEDIA_EXTENSIONS, VIDEO_EXTENSIONS, CleanConfig
from ..models import FieldChange
from .base import new_result
from .ebml_riff import probe_avi, probe_matroska, scrub_avi, scrub_matroska
from .exiftool import exiftool_available, read_tags, strip_media

# Containers exiftool cannot write — handled by the pure-Python EBML /
# RIFF scrubber (engines/ebml_riff.py) instead.
_EBML_EXTENSIONS = {"mkv", "webm"}
_RIFF_EXTENSIONS = {"avi"}

# Video tags that are container structure / codec info, not identity —
# filtered from the report so it doesn't look like they were "leaked".
_STRUCTURAL = {
    "Duration", "ImageWidth", "ImageHeight", "ImageSize", "VideoFrameRate", "AvgBitrate",
    "AudioBitrate", "AudioChannels", "AudioSampleRate", "SampleRate", "BitDepth", "Channels",
    "MajorBrand", "MinorVersion", "CompatibleBrands", "MediaDataSize", "MediaDataOffset",
    "MovieHeaderVersion", "TrackHeaderVersion", "MediaHeaderVersion", "Balance", "GraphicsMode",
    "OpColor", "CompressorID", "SourceImageWidth", "SourceImageHeight", "XResolution",
    "YResolution", "BitsPerSample", "NumChannels", "Encoding", "AudioFormat", "VideoCodec",
    "AudioCodec", "Rotation", "MatrixStructure", "PixelAspectRatio", "ColorRepresentation",
    "VideoFullRangeFlag", "ColorPrimaries", "TransferCharacteristics", "MatrixCoefficients",
}


class MediaEngine:
    name = "media"
    extensions = MEDIA_EXTENSIONS

    def probe(self, path: str, cfg: CleanConfig | None = None) -> list[FieldChange]:
        ext = _ext(path)
        if ext in AUDIO_EXTENSIONS:
            return _probe_audio(path)
        if ext in _EBML_EXTENSIONS:
            return [FieldChange("Matroska", f, v) for f, v in probe_matroska(path)]
        if ext in _RIFF_EXTENSIONS:
            return [FieldChange("RIFF", f, v) for f, v in probe_avi(path)]
        rows: list[FieldChange] = []
        for key, value in read_tags(path).items():
            group, _, tag = key.partition(":")
            if tag in _STRUCTURAL:
                continue
            rows.append(FieldChange(group or "Media", tag or key, value))
        return rows

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        ext = _ext(src)
        before = self.probe(src)

        if ext in AUDIO_EXTENSIONS:
            ok, msg = _strip_audio(src, dst)
            if not ok:
                return new_result(src, None, self.name, "error", error=msg)
            return new_result(src, dst, self.name, "cleaned", removed=before)

        # Matroska / WebM / AVI — exiftool can't write these; use the
        # pure-Python in-place Void/JUNK scrubber (works with --in-place).
        if ext in _EBML_EXTENSIONS or ext in _RIFF_EXTENSIONS:
            scrub = scrub_matroska if ext in _EBML_EXTENSIONS else scrub_avi
            ok, changes = scrub(src, dst)
            if not ok:
                return new_result(src, None, self.name, "error",
                                  error=changes[0][1] if changes else "could not parse container")
            result = new_result(src, dst, self.name, "cleaned", removed=before)
            result.reason = "in-place metadata blanking (track data untouched) — verify playback"
            return result

        # mp4 / mov / m4v / 3gp — exiftool
        if not exiftool_available():
            return new_result(src, None, self.name, "error",
                              error="video scrubbing needs the exiftool binary")
        ok, msg = strip_media(src, dst, is_video=True)
        if not ok:
            return new_result(src, None, self.name, "error", error=msg)
        result = new_result(src, dst, self.name, "cleaned", removed=before)
        result.reason = "video: metadata atoms cleared, track structure kept — verify playback"
        return result


# --- audio via mutagen --------------------------------------------------------


def _mutagen_file(path: str):
    import mutagen

    return mutagen.File(path)


def _probe_audio(path: str) -> list[FieldChange]:
    try:
        f = _mutagen_file(path)
    except Exception:  # noqa: BLE001 - unreadable / unknown container
        return []
    if f is None or not getattr(f, "tags", None):
        return []
    rows: list[FieldChange] = []
    try:
        for key in list(f.tags.keys()):
            val = str(f.tags[key])
            rows.append(FieldChange("Audio", str(key), val[:200]))
    except Exception:  # noqa: BLE001
        rows.append(FieldChange("Audio", "tags", "<present>"))
    # Embedded cover art (APIC / covr / METADATA_BLOCK_PICTURE / pictures)
    if _has_pictures(f):
        rows.append(FieldChange("Audio", "cover art", "<embedded image>"))
    return rows


def _has_pictures(f) -> bool:
    if getattr(f, "pictures", None):
        return True
    tags = getattr(f, "tags", None)
    if tags is None:
        return False
    keys = list(tags.keys())
    return any(k == "covr" or str(k).startswith("APIC") or str(k).upper() == "METADATA_BLOCK_PICTURE"
              for k in keys)


def _strip_audio(src: str, dst: str) -> tuple[bool, str]:
    try:
        import mutagen  # noqa: F401
    except ImportError:
        return False, "audio scrubbing needs mutagen — pip install 'metascrub[media]'"
    try:
        shutil.copyfile(src, dst)
    except OSError as exc:
        return False, f"could not stage output file: {exc}"
    try:
        f = _mutagen_file(dst)
        if f is None:
            return False, "mutagen could not read this file"
        if getattr(f, "tags", None):
            f.delete()
        for pic_attr in ("pictures",):
            if getattr(f, pic_attr, None):
                f.clear_pictures()
        f.save()
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"mutagen: {exc}"


def _ext(path: str) -> str:
    base = os.path.basename(path)
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


__all__ = ["MediaEngine", "AUDIO_EXTENSIONS", "VIDEO_EXTENSIONS"]
