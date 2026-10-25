import { AVATAR_THEMES, type AvatarTheme } from "./avatar-theme";

export type IdentityCrop = {
  mode: "fit" | "fill";
  zoom: number;
  x: number;
  y: number;
};
export type IdentityAppearance =
  | { kind: "default" }
  | { kind: "avatar"; token: AvatarTheme; mark: "initials" | "icon" }
  | {
      kind: "image";
      source: string;
      width: number;
      height: number;
      crop: IdentityCrop;
      rendered: string;
    };
export const DEFAULT_APPEARANCE: IdentityAppearance = { kind: "default" };
export const IDENTITY_EVENT = "cuadrao-local-identity-changed";
export const identityPreviewEnabled = () =>
  process.env.NODE_ENV === "development" &&
  process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
export const identityKey = (scope: string) => `cuadrao-identity-v1:${scope}`;
const imageData = (value: unknown): value is string =>
  typeof value === "string" &&
  value.length <= 1_500_000 &&
  /^data:image\/(png|webp|jpeg);base64,[A-Za-z0-9+/=]+$/.test(value);
export function parseAppearance(value: unknown): IdentityAppearance {
  if (!value || typeof value !== "object") return DEFAULT_APPEARANCE;
  const entry = value as Record<string, unknown>;
  const crop = entry.crop as IdentityCrop | undefined;
  if (
    entry.kind === "avatar" &&
    AVATAR_THEMES.some((theme) => theme.token === entry.token) &&
    ["icon", "initials"].includes(
      typeof entry.mark === "string" ? entry.mark : "",
    )
  )
    return {
      kind: "avatar",
      token: entry.token as AvatarTheme,
      mark: entry.mark as "icon" | "initials",
    };
  if (
    entry.kind === "image" &&
    imageData(entry.source) &&
    imageData(entry.rendered) &&
    typeof entry.width === "number" &&
    typeof entry.height === "number" &&
    entry.width > 0 &&
    entry.height > 0 &&
    entry.width <= 1280 &&
    entry.height <= 1280 &&
    crop &&
    ["fit", "fill"].includes(crop.mode) &&
    [crop.zoom, crop.x, crop.y].every(Number.isFinite) &&
    crop.zoom >= 1 &&
    crop.zoom <= 4 &&
    Math.abs(crop.x) <= 1 &&
    Math.abs(crop.y) <= 1
  )
    return {
      kind: "image",
      source: entry.source,
      width: entry.width,
      height: entry.height,
      crop: { mode: crop.mode, zoom: crop.zoom, x: crop.x, y: crop.y },
      rendered: entry.rendered,
    };
  return DEFAULT_APPEARANCE;
}
export function readAppearance(
  storage: Pick<Storage, "getItem">,
  scope: string,
): IdentityAppearance {
  try {
    return parseAppearance(
      JSON.parse(storage.getItem(identityKey(scope)) || "null"),
    );
  } catch {
    return DEFAULT_APPEARANCE;
  }
}
export function saveAppearance(
  storage: Pick<Storage, "setItem">,
  scope: string,
  appearance: IdentityAppearance,
) {
  const valid = parseAppearance(appearance);
  if (appearance.kind !== "default" && valid.kind === "default")
    throw new Error("invalid_image");
  storage.setItem(identityKey(scope), JSON.stringify(valid));
}
export function imageGeometry(
  width: number,
  height: number,
  crop: IdentityCrop,
  size = 256,
) {
  const scale =
    (crop.mode === "fit"
      ? Math.min(size / width, size / height)
      : Math.max(size / width, size / height)) * crop.zoom;
  const w = width * scale,
    h = height * scale;
  return {
    width: w,
    height: h,
    left: (size - w) / 2 + (crop.x * Math.abs(size - w)) / 2,
    top: (size - h) / 2 + (crop.y * Math.abs(size - h)) / 2,
  };
}
export function validateImageFile(
  file: Pick<File, "type" | "size">,
): "file_type" | "file_size" | null {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type))
    return "file_type";
  return file.size > 10 * 1024 * 1024 || file.size === 0 ? "file_size" : null;
}
function decode(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("file_decode"));
    image.src = source;
  });
}
export async function loadIdentityImage(file: File) {
  const error = validateImageFile(file);
  if (error) throw new Error(error);
  const sourceData = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () =>
      typeof reader.result === "string"
        ? resolve(reader.result)
        : reject(new Error("file_decode"));
    reader.onerror = () => reject(new Error("file_decode"));
    reader.readAsDataURL(file);
  });
  const image = await decode(sourceData);
  if (
    !image.naturalWidth ||
    !image.naturalHeight ||
    image.naturalWidth * image.naturalHeight > 40_000_000
  )
    throw new Error("file_decode");
  const ratio = Math.min(
    1,
    1280 / Math.max(image.naturalWidth, image.naturalHeight),
  );
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(image.naturalWidth * ratio);
  canvas.height = Math.round(image.naturalHeight * ratio);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("file_decode");
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  const source = canvas.toDataURL("image/webp", 0.82);
  if (!imageData(source)) throw new Error("file_size");
  return { source, width: canvas.width, height: canvas.height };
}
export async function renderIdentityImage(image: {
  source: string;
  width: number;
  height: number;
  crop: IdentityCrop;
}): Promise<IdentityAppearance> {
  const decoded = await decode(image.source),
    canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("file_decode");
  const frame = imageGeometry(image.width, image.height, image.crop, 512);
  context.drawImage(decoded, frame.left, frame.top, frame.width, frame.height);
  return {
    ...image,
    kind: "image",
    rendered: canvas.toDataURL("image/webp", 0.85),
  };
}
