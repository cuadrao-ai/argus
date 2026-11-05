"""Business identity images, separate from invoice branding."""

from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass
from typing import Annotated, Literal

from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field

from argus.domain.profile_images.images import MEDIA_TYPES, InvalidImage
from argus.domain.profile_images.objects import ProfileImageObjects

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_STORED_BYTES = 1024 * 1024


class Crop(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    mode: Literal["fit", "fill"] = "fill"
    zoom: float = Field(default=1, ge=1, le=4)
    x: float = Field(default=0, ge=-1, le=1)
    y: float = Field(default=0, ge=-1, le=1)


class DefaultAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["default"] = "default"


class AvatarAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["avatar"] = "avatar"
    token: Literal["ocean", "ember", "gold", "slate", "teal", "indigo", "plum"]
    mark: Literal["initials", "icon"]


class ImageAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["image"] = "image"
    asset_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    crop: Crop


Appearance = Annotated[
    DefaultAppearance | AvatarAppearance | ImageAppearance, Field(discriminator="kind")
]


@dataclass(frozen=True)
class WorkspaceAsset:
    id: str
    space_id: str
    sha256: str
    width: int
    height: int

    @property
    def source_path(self) -> str:
        return f"business/{self.space_id}/identity/{self.sha256}-source.webp"

    def render_path(self, crop: Crop) -> str:
        recipe = f"v1:{self.sha256}:{crop.model_dump_json()}"
        digest = hashlib.sha256(recipe.encode()).hexdigest()
        return f"business/{self.space_id}/identity/{digest}-render.webp"


def _webp(image: Image.Image) -> bytes:
    for quality in (82, 60):
        output = io.BytesIO()
        image.save(
            output, format="WEBP", quality=quality, exif=b"", icc_profile=b"", xmp=""
        )
        content = output.getvalue()
        if len(content) <= MAX_STORED_BYTES:
            return content
    raise InvalidImage("too_large")


def normalized_source(content: bytes, media_type: str) -> tuple[bytes, int, int]:
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise InvalidImage("too_large" if content else "empty")
    if media_type not in MEDIA_TYPES:
        raise InvalidImage("media_type")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(
                io.BytesIO(content), formats=[MEDIA_TYPES[media_type]]
            ) as source:
                if source.width * source.height > 40_000_000:
                    raise InvalidImage("too_many_pixels")
                if getattr(source, "n_frames", 1) != 1:
                    raise InvalidImage("animated")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGBA")
                image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                return _webp(image), image.width, image.height
    except InvalidImage:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InvalidImage("too_many_pixels") from None
    except Exception as error:
        raise InvalidImage("undecodable") from error


def render(objects: ProfileImageObjects, asset: WorkspaceAsset, crop: Crop) -> None:
    content = objects.read(asset.source_path)
    if hashlib.sha256(content).hexdigest() != asset.sha256:
        raise InvalidImage("source_changed")
    with Image.open(io.BytesIO(content), formats=["WEBP"]) as source:
        source.load()
        size = 512
        scale = (min if crop.mode == "fit" else max)(
            size / source.width, size / source.height
        ) * crop.zoom
        width, height = source.width * scale, source.height * scale
        left = (size - width) / 2 + crop.x * abs(size - width) / 2
        top = (size - height) / 2 + crop.y * abs(size - height) / 2
        image = source.convert("RGBA").transform(
            (size, size),
            Image.Transform.AFFINE,
            (1 / scale, 0, -left / scale, 0, 1 / scale, -top / scale),
            Image.Resampling.BICUBIC,
        )
        objects.put(asset.render_path(crop), _webp(image), "image/webp")
