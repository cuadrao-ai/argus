import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import {
  AVATAR_COLOR_THEMES,
  AVATAR_THEMES,
  avatarThemeClassName,
  avatarThemeStyle,
  type AvatarTheme,
} from "@/lib/avatar-theme";

const luminance = (hex: string) => {
  const [red, green, blue] = [1, 3, 5].map((start) => {
    const channel = parseInt(hex.slice(start, start + 2), 16) / 255;
    return channel <= 0.03928
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
};
const contrast = (first: string, second: string) => {
  const [dark, light] = [first, second]
    .map(luminance)
    .sort((one, two) => one - two);
  return (light + 0.05) / (dark + 0.05);
};
const tokenIn = (block: string, name: string) =>
  block.match(new RegExp(`${name}:\\s*([^;]+);`))?.[1].trim() ?? "";
/** A token is a hex color or `rgb(255 255 255 / a)`, painted over its surface. */
const over = (token: string, surface: string) => {
  const alpha = token.match(/rgb\(255 255 255 \/ ([\d.]+)\)/)?.[1];
  if (!alpha) return token;
  const channels = [1, 3, 5].map((start) => {
    const base = parseInt(surface.slice(start, start + 2), 16);
    return Math.round(base + (255 - base) * Number(alpha))
      .toString(16)
      .padStart(2, "0");
  });
  return `#${channels.join("")}`;
};

describe("avatar monogram themes", () => {
  test("keeps Argus's original neutral avatar as the deterministic default", () => {
    expect(AVATAR_THEMES).toHaveLength(7);
    expect(AVATAR_THEMES.map((theme) => theme.token)).toEqual([
      "ocean",
      "ember",
      "gold",
      "slate",
      "teal",
      "indigo",
      "plum",
    ] satisfies AvatarTheme[]);
    expect(avatarThemeClassName(undefined)).toBe(
      "bg-[#191c1f] text-white dark:bg-white/10",
    );
    expect(avatarThemeClassName("ocean")).toBe(
      "bg-[#191c1f] text-white dark:bg-white/10",
    );
    expect(avatarThemeStyle(undefined)).toBeUndefined();
    expect(avatarThemeStyle("ocean")).toBeUndefined();
  });

  test("paints the six colors flat, in tray order, on the saved tokens", () => {
    const fills = AVATAR_COLOR_THEMES.map(({ token }) => [
      token,
      avatarThemeStyle(token)?.backgroundColor,
    ]);
    expect(fills).toEqual([
      ["ember", "#051F20"],
      ["gold", "#0B2B26"],
      ["slate", "#163832"],
      ["teal", "#235347"],
      ["indigo", "#8EB69B"],
      ["plum", "#DAF1DE"],
    ]);
    expect(AVATAR_THEMES.map(({ token }) => token)).toEqual([
      "ocean",
      ...AVATAR_COLOR_THEMES.map(({ token }) => token),
    ]);
    for (const { token } of AVATAR_COLOR_THEMES) {
      expect(avatarThemeClassName(token)).toBe("");
    }
  });

  test("initials keep 4.5:1 on every color", () => {
    for (const { token } of AVATAR_COLOR_THEMES) {
      const style = avatarThemeStyle(token)!;
      expect(contrast(style.backgroundColor, style.color)).toBeGreaterThanOrEqual(4.5);
    }
  });

  test("the tile border keeps 3:1 on both tray surfaces and against the colors it has to hold", () => {
    const css = readFileSync("app/globals.css", "utf8");
    const root = css.slice(css.indexOf(":root"), css.indexOf(".dark {"));
    const dark = css.slice(css.indexOf(".dark {"), css.indexOf("body {"));
    const lightBorder = tokenIn(root, "--segment-thumb-border");
    expect(contrast(lightBorder, "#ffffff")).toBeGreaterThanOrEqual(3);
    expect(contrast(lightBorder, "#DAF1DE")).toBeGreaterThanOrEqual(3);
    const drawerSurface = "#1b1d20";
    for (const surface of [drawerSurface, tokenIn(dark, "--cuadrao-menu-surface")]) {
      const darkBorder = over(tokenIn(dark, "--segment-thumb-border"), surface);
      expect(contrast(darkBorder, surface)).toBeGreaterThanOrEqual(3);
      for (const fill of ["#051F20", "#0B2B26", "#163832"])
        expect(contrast(darkBorder, fill)).toBeGreaterThanOrEqual(3);
    }
  });

  test("the saved tokens stay one set in the web, the API and the Business appearance", () => {
    const web = [...AVATAR_THEMES.map(({ token }) => token)].sort();
    const literal = (path: string, pattern: RegExp) =>
      [...(readFileSync(path, "utf8").match(pattern)?.[1] ?? "").matchAll(/"(\w+)"/g)]
        .map((match) => match[1])
        .sort();
    expect(literal("../src/argus/api/schemas.py", /AvatarTheme = Literal\[([^\]]+)\]/)).toEqual(web);
    expect(literal("../src/argus/domain/business/workspace_images.py", /token: Literal\[([^\]]+)\]/)).toEqual(web);
    expect(literal("lib/business-profile-api.ts", /token: z\.enum\(\[([^\]]+)\]/)).toEqual(web);
  });

  test("labels every selectable avatar theme in English and Latin American Spanish", async () => {
    const [en, es] = await Promise.all([
      import("@/public/locales/en/common.json"),
      import("@/public/locales/es-419/common.json"),
    ]);
    const expectedThemes = new Set(AVATAR_THEMES.map((theme) => theme.token));

    for (const locale of [en.default, es.default]) {
      const avatarTheme = locale.settings.profile.avatar_theme;
      expect(new Set(Object.keys(avatarTheme.themes))).toEqual(expectedThemes);
      expect(avatarTheme.label.trim()).not.toBe("");
      expect(avatarTheme.change.trim()).not.toBe("");
      expect(avatarTheme.close.trim()).not.toBe("");
      expect(avatarTheme.hide.trim()).not.toBe("");
      for (const theme of AVATAR_THEMES) {
        expect(avatarTheme.themes[theme.token].trim()).not.toBe("");
      }
    }

    expect(en.default.settings.profile.avatar_theme.label).toBe("Avatar color");
    expect(es.default.settings.profile.avatar_theme.label).toBe(
      "Color del avatar",
    );
  });
});
