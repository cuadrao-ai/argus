import { describe, expect, test } from "bun:test";

import { businessContent } from "../components/content";
import { siteCopy } from "../components/site-copy";
import { landingCopy } from "../components/landing/landing-copy";
import { PAGE_METADATA } from "../lib/page-metadata";

function strings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(strings);
  if (value && typeof value === "object") return Object.values(value).flatMap(strings);
  return [];
}

describe("English copy", () => {
  test.each([
    ["site copy", siteCopy.en],
    ["landing copy", landingCopy.en],
    ["page content", businessContent.en],
    ["page metadata", PAGE_METADATA.en],
  ])("%s uses the typographic apostrophe", (_name, copy) => {
    expect(strings(copy).filter((text) => /[A-Za-z]'[A-Za-z]/.test(text))).toEqual([]);
  });
});
