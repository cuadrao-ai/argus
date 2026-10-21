import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const WEB = path.resolve(import.meta.dir, "..");
const LONG_DASH = /—|\\u2014|&mdash;|&#8212;|&#x2014;/i;

/** A file that may hold the long dash, with the reason it is not an unknown amount. Empty today. */
const ALLOWED: Record<string, string> = {};

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return sources(full);
    return /\.(ts|tsx|css)$/.test(name) ? [full] : [];
  });
}

describe("an unknown amount is a plain short dash", () => {
  test("no Business source writes the long dash", () => {
    const files = [...sources(path.join(WEB, "components/business-app")), ...readdirSync(path.join(WEB, "lib")).filter((name) => name.startsWith("business-")).map((name) => path.join(WEB, "lib", name))];
    const offenders = files
      .map((file) => path.relative(WEB, file))
      .filter((file) => LONG_DASH.test(readFileSync(path.join(WEB, file), "utf8")) && !(file in ALLOWED));
    expect(offenders).toEqual([]);
  });

  test("the allowlist names a reason and a file that still holds the long dash", () => {
    for (const [file, reason] of Object.entries(ALLOWED)) {
      expect(reason.length).toBeGreaterThan(10);
      expect(LONG_DASH.test(readFileSync(path.join(WEB, file), "utf8"))).toBe(true);
    }
  });

  test("the Business locales never use it either", () => {
    for (const language of ["es-419", "en"]) {
      const business = JSON.stringify((JSON.parse(readFileSync(path.join(WEB, `public/locales/${language}/common.json`), "utf8")) as { business: unknown }).business);
      expect(business.includes("—")).toBe(false);
    }
  });
});
