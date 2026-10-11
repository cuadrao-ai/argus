import { test } from "bun:test";
import assert from "node:assert/strict";
import { conversationTabTitle } from "../lib/chat-title-display";

for (const surface of ["business", "personal"] as const) test(`tab title respects the ${surface} surface after hydration`, () => {
  const brand = surface === "business" ? "Cuadrao" : "Argus";
  assert.equal(conversationTabTitle(null, false, surface), brand);
  assert.equal(conversationTabTitle({ title: "Internal default", title_source: "system_default" }, true, surface), brand);
  for (const title_source of ["ai_generated", "user_renamed"] as const) {
    const conversation = { title: "Receipt review", title_source };
    assert.equal(conversationTabTitle(conversation, true, surface), `Receipt review · ${brand}`);
    assert.equal(conversationTabTitle(conversation, false, surface), brand);
  }
});
