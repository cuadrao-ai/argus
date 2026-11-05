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
