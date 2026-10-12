import { describe, expect, test } from "bun:test";
import {
  SOCIAL_PLATFORMS,
  socialPreviewEnabled,
  visibleSocials,
  type SocialPlatform,
} from "../lib/social";

const live: SocialPlatform = { id: "youtube", label: "YouTube", href: "https://example.test/y" };

describe("social links", () => {
  test("nothing shows before any account exists and the preview is off", () => {
    expect(visibleSocials(SOCIAL_PLATFORMS, false)).toEqual([]);
  });

  test("the preview shows every platform", () => {
    expect(visibleSocials(SOCIAL_PLATFORMS, true).map((p) => p.id)).toEqual([
      "tiktok",
      "instagram",
      "youtube",
    ]);
  });

  test("a platform with an account shows without the preview", () => {
    const list = [SOCIAL_PLATFORMS[0], live];
    expect(visibleSocials(list, false)).toEqual([live]);
  });

  test("only the value 1 turns the preview on", () => {
    expect(socialPreviewEnabled("1")).toBe(true);
    for (const value of [undefined, "", "0", "true", "yes"]) {
      expect(socialPreviewEnabled(value)).toBe(false);
    }
  });
});
