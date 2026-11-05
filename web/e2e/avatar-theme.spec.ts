import { expect, test, type Page, type Route } from "@playwright/test";

type RegisteredProfile = {
  id: string;
  email: string;
  username: string;
  display_name: string;
  language: "en";
  locale: "en-US";
  avatar_theme:
    "ocean" | "ember" | "gold" | "slate" | "teal" | "indigo" | "plum";
};

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockRegisteredProfile(page: Page) {
  const profile: RegisteredProfile = {
    id: "avatar-user",
    email: "avatar@example.com",
    username: "avatar-user",
    display_name: "Avatar User",
    language: "en",
    locale: "en-US",
    avatar_theme: "ocean",
  };
  const avatarThemePatches: string[] = [];

  await page.route("**/api/v1/me", async (route) => {
    if (route.request().method() === "PATCH") {
      const patch = route.request().postDataJSON() as {
        avatar_theme?: RegisteredProfile["avatar_theme"];
      };
      if (patch.avatar_theme) {
        profile.avatar_theme = patch.avatar_theme;
        avatarThemePatches.push(patch.avatar_theme);
      }
    }
    await fulfillJson(route, { user: profile, account_kind: "registered" });
  });

  await page.route("**/api/v1/conversations", async (route) => {
    await fulfillJson(route, { items: [], next_cursor: null });
  });

  return { avatarThemePatches };
}

async function openProfileModal(page: Page) {
  const settingsTrigger = page.getByRole("button", { name: "Settings" });
  await settingsTrigger.focus();
  await page.keyboard.press("Enter");
  const profileMenuItem = page.getByRole("button", {
    name: "Profile",
    exact: true,
  });
  await profileMenuItem.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Profile" });
  await expect(dialog).toBeVisible();
  return dialog;
}

test("avatar drawer persists keyboard selection and returns focus on dismiss", async ({
  page,
}) => {
  const { avatarThemePatches } = await mockRegisteredProfile(page);
  await page.goto("/chat", { waitUntil: "networkidle" });

  const dialog = await openProfileModal(page);
  const avatarTrigger = dialog.getByRole("button", { name: "Edit avatar" });
  const editCue = avatarTrigger.locator("span[aria-hidden='true']");
  await expect(avatarTrigger).toHaveAttribute("aria-expanded", "false");
  await expect(editCue).toHaveCSS("opacity", "1");

  await avatarTrigger.click();
  await expect(avatarTrigger).toHaveAttribute("aria-expanded", "true");

  const picker = dialog.getByRole("radiogroup", { name: "Avatar color" });
  const defaultAvatar = picker.getByRole("radio", { name: "Default" });
  const nightAvatar = picker.getByRole("radio", { name: "Night" });
  const mintAvatar = picker.getByRole("radio", { name: "Mint" });

  await expect(defaultAvatar).toHaveAttribute("aria-checked", "true");
  await expect(defaultAvatar).toHaveAttribute("tabindex", "0");
  await expect(defaultAvatar).toBeFocused();

  await page.keyboard.press("ArrowRight");
  await expect(nightAvatar).toHaveAttribute("aria-checked", "true");
  await expect(nightAvatar).toHaveAttribute("tabindex", "0");
  await expect(nightAvatar).toBeFocused();
  await expect.poll(() => avatarThemePatches).toEqual(["ember"]);
  await expect(picker).not.toHaveAttribute("aria-busy", "true");

  await page.keyboard.press("End");
  await expect(mintAvatar).toHaveAttribute("aria-checked", "true");
  await expect(mintAvatar).toBeFocused();
  await expect.poll(() => avatarThemePatches).toEqual(["ember", "plum"]);
  await expect(picker).not.toHaveAttribute("aria-busy", "true");

  await page.keyboard.press("Home");
  await expect(defaultAvatar).toHaveAttribute("aria-checked", "true");
  await expect(defaultAvatar).toBeFocused();
  await expect
    .poll(() => avatarThemePatches)
    .toEqual(["ember", "plum", "ocean"]);
  await expect(picker).not.toHaveAttribute("aria-busy", "true");

  await page.keyboard.press("Escape");
  await expect(avatarTrigger).toHaveAttribute("aria-expanded", "false");
  await expect(avatarTrigger).toBeFocused();
});
