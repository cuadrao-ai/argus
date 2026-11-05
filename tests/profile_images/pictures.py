"""Pictures the profile image tests upload, built with Pillow."""

from __future__ import annotations

import io

from PIL import ExifTags, Image, ImageCms

RED = (220, 30, 30)
BLUE = (30, 30, 220)
GPS_IFD = ExifTags.IFD.GPSInfo
ORIENTATION = 0x0112


def halves(width: int = 300, height: int = 200, mode: str = "RGB") -> Image.Image:
    """Left half red, right half blue, so a test can see where each ends up."""

    image = Image.new(mode, (width, height), RED)
    image.paste(BLUE, (width // 2, 0, width, height))
    return image


def png(width: int = 300, height: int = 200, *, alpha: bool = False) -> bytes:
    """With ``alpha`` the blue half is fully transparent, as a logo on no background."""

    image = halves(width, height, "RGBA" if alpha else "RGB")
    if alpha:
        image.paste((*BLUE, 0), (width // 2, 0, width, height))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def webp(width: int = 300, height: int = 200) -> bytes:
    output = io.BytesIO()
    halves(width, height).save(output, format="WEBP")
    return output.getvalue()


def jpeg_with_gps(width: int = 300, height: int = 200, *, orientation: int = 1) -> bytes:
    """A JPEG that carries an EXIF orientation, a GPS position and an ICC profile."""

    exif = Image.Exif()
    exif[ORIENTATION] = orientation
    gps = exif.get_ifd(GPS_IFD)
    gps[1] = "N"
    gps[2] = (18.0, 28.0, 0.0)
    gps[3] = "W"
    gps[4] = (69.0, 54.0, 0.0)
    output = io.BytesIO()
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    halves(width, height).save(
        output, format="JPEG", quality=90, exif=exif.tobytes(), icc_profile=icc
    )
    return output.getvalue()


def animated_webp() -> bytes:
    output = io.BytesIO()
    first, second = halves(), halves().rotate(180)
    first.save(output, format="WEBP", save_all=True, append_images=[second], duration=100)
    return output.getvalue()
