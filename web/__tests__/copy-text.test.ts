import assert from "node:assert/strict";
import { test } from "bun:test";

import { copyText } from "../lib/copy-text";

test("the clipboard receives the full text and the call never throws", async () => {
  const written: string[] = [];
  assert.equal(await copyText("CUADRAO ABCD1234", { writeText: async (value) => { written.push(value); } }, null), true);
  assert.deepEqual(written, ["CUADRAO ABCD1234"]);
  assert.equal(await copyText("CUADRAO ABCD1234", { writeText: async () => { throw new Error("denied"); } }, null), false);
  assert.equal(await copyText("CUADRAO ABCD1234", null, null), false);
});
