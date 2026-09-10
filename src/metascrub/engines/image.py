from __future__ import annotations

from ..config import IMAGE_EXTENSIONS, CleanConfig
from ..models import FieldChange
from .base import new_result
from .exiftool import exiftool_available, read_tags, strip_all


class ImageEngine:
    name = "image"
    extensions = IMAGE_EXTENSIONS

    def probe(self, path: str, cfg: CleanConfig | None = None) -> list[FieldChange]:
        rows: list[FieldChange] = []
        for key, value in read_tags(path).items():
            group, _, tag = key.partition(":")
            rows.append(FieldChange(group or "Meta", tag or key, value))
        return rows

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        before = read_tags(src)

        if exiftool_available():
            ok, msg = strip_all(
                src, dst,
                keep_color_profile=cfg.keep_color_profile,
                keep_orientation=cfg.keep_orientation,
            )
            if not ok:
                return new_result(src, None, self.name, "error", error=msg)
        else:
            ok, msg = _pillow_strip(src, dst, cfg)
            if not ok:
                return new_result(
                    src, None, self.name, "error",
                    error=f"exiftool not found and Pillow fallback failed: {msg}",
                )

        removed = [
            FieldChange(k.partition(":")[0] or "Meta", k.partition(":")[2] or k, v)
            for k, v in before.items()
        ]
        return new_result(src, dst, self.name, "cleaned", removed=removed)


def _pillow_strip(src: str, dst: str, cfg: CleanConfig) -> tuple[bool, str]:
    """Last-resort path when exiftool is missing. Re-encodes the pixels
    without any EXIF/text chunks. Only jpg/png/webp/tiff; loses everything
    including the ICC profile unless keep_color_profile is set.
    """
    try:
        from PIL import Image
    except ImportError:
        return False, "install 'metascrub[image-fallback]' or the exiftool binary"

    try:
        with Image.open(src) as im:
            icc = im.info.get("icc_profile") if cfg.keep_color_profile else None
            exif_bytes = None
            if cfg.keep_orientation:
                orient = im.getexif().get(0x0112)
                if orient:
                    from PIL import Image as _I

                    ex = _I.Exif()
                    ex[0x0112] = orient
                    exif_bytes = ex.tobytes()
            save_kw: dict = {}
            if icc:
                save_kw["icc_profile"] = icc
            if exif_bytes:
                save_kw["exif"] = exif_bytes
            data = list(im.getdata())
            clean = Image.new(im.mode, im.size)
            clean.putdata(data)
            clean.save(dst, format=im.format, **save_kw)
        return True, "pillow"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
