import { expect, test } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

// A receipt's status word is the server's `bandeja_group.label`, drawn from `business.bandeja.label.*`.
// The web once worked out a word of its own from the receipt's status; that owner is gone and stays gone.
const WEB = path.resolve(import.meta.dir, "..");
const SOURCE = /\.(ts|tsx)$/;
// Split so a grep of the tree for the old names finds nothing, this file included.
const OLD_OWNER = new RegExp([
  "useReceipt" + "StateWord", "receipt-state" + "-word", "receipt" + "Tag\\b",
  // The legacy tag pill, its tag type, its palette of words and their locale block.
  "foundation/Status" + "Pill", "statusName" + "ForTag", "Reception" + "Tag\\b", "reception" + "-status", "BUSINESS" + "_STATUS", "business\\.status" + "\\.",
].join("|"));

test("no source works out a receipt's status word in the web", () => {
  const found = ["app", "components", "lib"].flatMap((root) =>
    (readdirSync(path.join(WEB, root), { recursive: true }) as string[])
      .filter((file) => SOURCE.test(file))
      .map((file) => path.join(root, file))
      .filter((file) => OLD_OWNER.test(readFileSync(path.join(WEB, file), "utf8"))));
  expect(found).toEqual([]);
});

test("the locales hold no status words for the web to pick from", () => {
  for (const language of ["es-419", "en"]) {
    const copy = JSON.parse(readFileSync(path.join(WEB, "public/locales", language, "common.json"), "utf8"));
    expect(Object.keys(copy.business)).not.toContain("status");
  }
});
