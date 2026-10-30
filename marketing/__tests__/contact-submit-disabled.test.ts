import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";

const read = (name: string) =>
  readFileSync(new URL(`../components/${name}`, import.meta.url), "utf8");

const business = read("business.module.css");
const form = read("contact-form.tsx");

test("the contact submit control keeps the sending label and the unavailable signals", () => {
  expect(form).toContain("disabled={!hydrated}");
  expect(form).toContain("aria-disabled={sending}");
  expect(form).toContain("{sending ? copy.sending : copy.submit}");
  expect(form).toContain("if (pending.current) return;");
});

test("unavailable submit paint uses palette colors, not a fade", () => {
  const block =
    business.match(
      /\.formFields > button\.submit:is\(:disabled, \[aria-disabled="true"\]\) \{([^}]*)\}/,
    )?.[1] ?? "";
  expect(block).toContain("background: var(--accent)");
  expect(block).toContain("color: var(--ink) !important");
  expect(block).toContain("border-color: var(--muted)");
  expect(block).toContain("cursor: not-allowed");
  expect(block).toContain("opacity: 1");
  expect(block).not.toContain("opacity: 0.5");
  expect(business).toMatch(/\.submit \{\s*background: var\(--cta-rest\);/);
});
