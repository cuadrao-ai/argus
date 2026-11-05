"""The one picture shape the server stores: a 256 px WebP square, no metadata."""

from __future__ import annotations

import io
import warnings

from PIL import Image, ImageOps

SIZE = 256
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000
MIN_SIDE = 64
MEDIA_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
OUTPUT_MEDIA_TYPE = "image/webp"


class InvalidImage(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def square_webp(content: bytes, media_type: str) -> bytes:
    """``content`` as a SIZE px WebP square: oriented by its EXIF, then
    center-cropped and resized, saved with empty EXIF, ICC and XMP so no tag
    of the upload (GPS included) survives."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content), formats=[MEDIA_TYPES[media_type]]) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise InvalidImage("too_many_pixels")
                if min(source.width, source.height) < MIN_SIDE:
                    raise InvalidImage("too_small")
                if getattr(source, "n_frames", 1) != 1:
                    raise InvalidImage("animated")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                mode = "RGBA" if oriented.has_transparency_data else "RGB"
                fitted = ImageOps.fit(
                    oriented.convert(mode), (SIZE, SIZE), Image.Resampling.LANCZOS
                )
    except InvalidImage:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InvalidImage("too_many_pixels") from None
    except Exception as error:
        raise InvalidImage("undecodable") from error
    output = io.BytesIO()
    fitted.save(output, format="WEBP", quality=85, exif=b"", icc_profile=b"", xmp="")
    return output.getvalue()
