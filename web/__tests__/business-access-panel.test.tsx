import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { AccessList } from "../components/business-app/BusinessAccessPanel";
import type { BusinessAccess } from "../lib/business-api";

const ACCESS: BusinessAccess = {
  grants: [
    { id: "g-owner", email: null, display_name: "Lucía", capabilities: ["read", "prepare", "approve"], created_at: "2026-10-01T12:00:00Z", owner: true },
    { id: "g-marta", email: "marta@example.test", display_name: "Marta", capabilities: ["read", "prepare"], created_at: "2026-10-05T15:30:00Z", owner: false },
  ],
  invites: [{ id: "i-1", email: "nuevo@example.test", created_at: "2026-10-11T10:00:00Z", expires_at: "2026-10-25T10:00:00Z" }],
};

async function render(language: "es-419" | "en", access: BusinessAccess = ACCESS) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <AccessList access={access} busyId={null} onRemove={() => undefined} />
    </I18nextProvider>,
  );
}

describe("Business access list", () => {
  test("Spanish: the owner is locked, the accountant can be removed, the invite shows its expiry", async () => {
    const html = await render("es-419");
    assert.ok(html.includes("Dueño"));
    assert.ok(html.includes("Tu propio acceso no se puede quitar."));
    assert.ok(html.includes("Marta · marta@example.test"));
    assert.ok(html.includes("Ve y prepara"));
    assert.ok(html.includes("Invitaciones pendientes"));
    assert.ok(html.includes("nuevo@example.test"));
    assert.ok(html.includes("Cancelar invitación"));
    assert.equal((html.match(/Quitar acceso/g) ?? []).length, 1);
    assert.ok(!html.includes("—"));
  });

  test("English follows the same rule and no invites renders no pending section", async () => {
    const html = await render("en", { grants: ACCESS.grants, invites: [] });
    assert.ok(html.includes("Owner"));
    assert.ok(html.includes("Reads and prepares"));
    assert.ok(html.includes("Remove access"));
    assert.ok(!html.includes("Pending invites"));
    assert.ok(!html.includes("approve"));
  });
});
