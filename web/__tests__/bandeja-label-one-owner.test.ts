import { expect, test } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

// A receipt's status word is the server's `bandeja_group.label`, drawn from `business.bandeja.label.*`.
// The web once worked out a word of its own from the receipt's status; that owner is gone and stays gone.
const WEB = path.resolve(import.meta.dir, "..");
const SOURCE = /\.(ts|tsx)$/;

test("no source works out a receipt's status word in the web", () => {
  const found = ["app", "components", "lib"].flatMap((root) =>
    (readdirSync(path.join(WEB, root), { recursive: true }) as string[])
      .filter((file) => SOURCE.test(file))
      .map((file) => path.join(root, file))
      .filter((file) => /useReceiptStateWord|receipt-state-word|receiptTag\b/.test(readFileSync(path.join(WEB, file), "utf8"))));
  expect(found).toEqual([]);
});
