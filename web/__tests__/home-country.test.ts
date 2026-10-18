import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  COUNTRY_CODES,
  CURRENCY_CODES,
  browserRegion,
  countryName,
  currencyName,
} from "../lib/home-country";

describe("the home country picker's codes", () => {
  test("a browser suggests only a country its language tag names outright", () => {
    expect(browserRegion(["es-MX", "en-US"])).toBe("MX");
    expect(browserRegion(["en-DO"])).toBe("DO");
    // A bare language is not a guess at a country, and a region is not a country.
    expect(browserRegion(["es", "en"])).toBeNull();
    expect(browserRegion(["es-419"])).toBeNull();
    expect(browserRegion(["en-EU"])).toBeNull();
    expect(browserRegion([])).toBeNull();
  });

  test("names come in the reader's language, never as a bare code", () => {
    const english = countryName("MX", "en");
    const spanish = countryName("MX", "es-419");
    expect(english).not.toBe("MX");
    expect(spanish).not.toBe("MX");
    expect(spanish).not.toBe(english);
    expect(currencyName("MXN", "es-419")).not.toBe("MXN");
  });

  test("the offered codes have the shape the account accepts", () => {
    expect(COUNTRY_CODES.every((code) => /^[A-Z]{2}$/.test(code))).toBe(true);
    expect(CURRENCY_CODES.every((code) => /^[A-Z]{3}$/.test(code))).toBe(true);
    expect(COUNTRY_CODES).toContain("DO");
    expect(CURRENCY_CODES).toContain("DOP");
  });

  test("every text field in a Preferences panel is at least 16px, so iOS never zooms", () => {
    // Derived from the registry: whatever the Preferences submenu can open.
    const panels = readFileSync(
      join(import.meta.dir, "../components/sidebar/ProfileSettingsPanels.tsx"),
      "utf-8",
    );
    const imports = new Map(
      [...panels.matchAll(/import (\w+) from "@\/components\/settings\/(\w+)"/g)].map(
        (match) => [match[1], match[2]],
      ),
    );
    const preferences = [
      ...panels.matchAll(/\w+: \{\s*parent: "settings",\s*render: [^<]*<(\w+)/g),
    ].map((match) => imports.get(match[1]));
    expect(preferences).toContain("HomeCountryModal");
    expect(preferences).toContain("LanguageModal");
    const sizes: number[] = [];
    for (const file of preferences) {
      const source = readFileSync(
        join(import.meta.dir, `../components/settings/${file}.tsx`),
        "utf-8",
      );
      // A whole element, so an arrow function inside a handler cannot end it early.
      for (const field of source.matchAll(
        /<(input|textarea|select)\b[\s\S]*?(?:\/>|<\/\1>)/g,
      )) {
        const className = field[0].match(/className="([^"]*)"/)?.[1] ?? "";
        sizes.push(
          ...[...className.matchAll(/text-\[(\d+)px\]/g)].map((size) => Number(size[1])),
        );
      }
    }
    expect(sizes.length).toBeGreaterThanOrEqual(2);
    expect(sizes.filter((size) => size < 16)).toEqual([]);
  });

  test("only a registered Personal account is offered the setting", () => {
    // A guest has no account to keep a country in, and the API omits it for guests.
    const menu = readFileSync(
      join(import.meta.dir, "../components/sidebar/ProfileMenu.tsx"),
      "utf-8",
    );
    expect(menu).toContain('const homeCountryAvailable = !isBusiness && accountKind === "registered";');
    const opens = [...menu.matchAll(/openModal\("country"\)/g)];
    // The Preferences row and its quick jump, each behind the same gate.
    expect(opens).toHaveLength(2);
    for (const open of opens) {
      expect(menu.slice(Math.max(0, open.index - 200), open.index)).toContain(
        "homeCountryAvailable",
      );
    }
  });
});
