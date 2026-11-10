const LIGHT_INK = "#FFFFFF";
const DARK_INK = "#051F20";

// The tokens are saved in `profiles.avatar_theme` and in Business appearance,
// so a color changes here and the token stays.
export const AVATAR_COLOR_THEMES = [
  { token: "ember", backgroundColor: "#051F20", color: LIGHT_INK },
  { token: "gold", backgroundColor: "#0B2B26", color: LIGHT_INK },
  { token: "slate", backgroundColor: "#163832", color: LIGHT_INK },
  { token: "teal", backgroundColor: "#235347", color: LIGHT_INK },
  { token: "indigo", backgroundColor: "#8EB69B", color: DARK_INK },
  { token: "plum", backgroundColor: "#DAF1DE", color: DARK_INK },
] as const;

export const AVATAR_THEMES = [
  { token: "ocean" },
  ...AVATAR_COLOR_THEMES,
] as const;

export type AvatarTheme = (typeof AVATAR_THEMES)[number]["token"];

const colorTheme = (theme: AvatarTheme | undefined) =>
  AVATAR_COLOR_THEMES.find(({ token }) => token === theme);

export function avatarThemeClassName(theme: AvatarTheme | undefined): string {
  return colorTheme(theme) ? "" : "bg-[#191c1f] text-white dark:bg-white/10";
}

export function avatarThemeStyle(theme: AvatarTheme | undefined) {
  const match = colorTheme(theme);
  return (
    match && { backgroundColor: match.backgroundColor, color: match.color }
  );
}

const TINTS = [
  { bg: "#e3ebe1", fg: "#2f5a49" },
  { bg: "#f2e8c9", fg: "#5c4910" },
  { bg: "#dde7ef", fg: "#2c5170" },
  { bg: "#f1e0ea", fg: "#7a2f57" },
  { bg: "#e7e2f3", fg: "#4a3d78" },
  { bg: "#e0eeeb", fg: "#1f5c55" },
  { bg: "#f3e2d9", fg: "#7a3d1c" },
  { bg: "#e8e8e3", fg: "#3d4a45" },
] as const;

function tintFor(seed: string) {
  let hash = 0;
  for (const char of seed.toLocaleLowerCase()) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
  return TINTS[hash % TINTS.length];
}

export function personAvatarAppearance(
  name: string | null | undefined,
  theme: AvatarTheme | undefined,
) {
  if (theme !== undefined) {
    return { className: avatarThemeClassName(theme), style: avatarThemeStyle(theme) };
  }
  const tint = tintFor(name ?? "");
  return { className: "", style: { backgroundColor: tint.bg, color: tint.fg } };
}
