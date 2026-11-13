import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "bun:test";

const businessApp = join(import.meta.dir, "../components/business-app");
const read = (path: string) => readFileSync(join(businessApp, path), "utf-8");
const css = read("recepcion/reception.module.css");
const rule = (selector: string) => css.split("\n").find(line => line.startsWith(`${selector},`) || line.startsWith(`${selector} {`));

test("a row tints and shows its trash on hover or keyboard focus, never on focus a mouse click leaves behind", () => {
  assert.doesNotMatch(css, /\.row:focus-within/, "the panel returns focus to the row after a click, so focus-within keeps it tinted");
  assert.match(rule(".row:hover") ?? "", /^\.row:hover,\.row:has\(:focus-visible\) \{ background:/);
  assert.match(rule(".row:hover .trashAction") ?? "", /^\.row:hover \.trashAction,\.row:has\(:focus-visible\) \.trashAction \{ opacity:1; \}/);
});

test("an Eliminados row shows its purge action on hover or keyboard focus, never after its panel closes from a click", () => {
  assert.match(rule(".deletedRow:hover .purgeAction") ?? "", /^\.deletedRow:hover \.purgeAction,\.deletedRow:has\(:focus-visible\) \.purgeAction \{ opacity:1; \}/);
});

test("no Business app row reveals or tints on focus-within, since a closed panel or dialog returns focus after a click", () => {
  const sheets = readdirSync(businessApp, { recursive: true, encoding: "utf-8" }).filter(name => name.endsWith(".module.css")).sort();
  const selectors = sheets.flatMap(name => (read(name).match(/[^\n{}]*:focus-within[^{]*/g) ?? []).map(selector => `${name}: ${selector.replace(/\s+/g, " ").trim()}`));
  assert.deepEqual(selectors, ["invoicing/invoicing-preview.module.css: .search:focus-within"], "a text field ring is the only focus-within left: typing focus is always visible");
});
