import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "bun:test";

const css = readFileSync(join(import.meta.dir, "../components/business-app/recepcion/reception.module.css"), "utf-8");
const rule = (selector: string) => css.split("\n").find(line => line.startsWith(`${selector},`) || line.startsWith(`${selector} {`));

test("a row tints and shows its trash on hover or keyboard focus, never on focus a mouse click leaves behind", () => {
  assert.doesNotMatch(css, /\.row:focus-within/, "the panel returns focus to the row after a click, so focus-within keeps it tinted");
  assert.match(rule(".row:hover") ?? "", /^\.row:hover,\.row:has\(:focus-visible\) \{ background:/);
  assert.match(rule(".row:hover .trashAction") ?? "", /^\.row:hover \.trashAction,\.row:has\(:focus-visible\) \.trashAction \{ opacity:1; \}/);
});
