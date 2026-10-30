import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const read = (name: string) =>
  readFileSync(new URL(`../components/${name}`, import.meta.url), "utf8");

test("the consent glyph stays 18px inside a 44px hit area", () => {
  const css = read("business.module.css");
  const row = css.match(/\.pilotRow \{([^}]*)\}/)?.[1] ?? "";
  const input = css.match(/\.pilotRow input \{([^}]*)\}/)?.[1] ?? "";
  const pad = css.match(/\.pilotRow::before \{([^}]*)\}/)?.[1] ?? "";
  expect(row).toContain("min-height: 44px");
  expect(input).toContain("flex: 0 0 18px");
  expect(input).toContain("width: 18px");
  expect(input).toContain("height: 18px");
  expect(pad).toContain("width: 44px");
  expect(pad).toContain("height: 44px");
  expect(pad).not.toContain("margin");
});

test("the privacy link grows by padding and the contact page focus ring uses the green", () => {
  const css = read("business.module.css");
  const link = css.match(/\.formPrivacy a \{([^}]*)\}/)?.[1] ?? "";
  expect(link).toContain("min-width: 44px");
  expect(link).toContain("min-height: 44px");
  expect(link).toContain("padding: 12px 8px");
  expect(link).not.toContain("margin");
  expect(css).toContain('outline: 2px solid var(--cta-rest)');
  expect(read("business-pages.tsx")).toContain('data-page="contact"');
  expect(css).toContain("min-height: 44px;\n  padding-block: 4px;");
  expect(css).not.toMatch(/\.businessFooterGrid nav > a \{[^}]*margin/);
});
