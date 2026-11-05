import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { AccessList } from "../components/business-app/BusinessAccessPanel";
import spanish from "@/public/locales/es-419/common.json";
import type { BusinessAccessInvite } from "../lib/business-api";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("expired message stays until the owner's explicit resend and busy prevents another click", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  const sent: BusinessAccessInvite[] = [];
  const invite: BusinessAccessInvite = { id: "invite-one", email: "contadora@example.test", created_at: "2026-10-01T03:00:00Z", expires_at: "2026-10-08T03:00:00Z", state: "expired" };
  const render = async (busyId: string | null) => {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><AccessList access={{ grants: [], invites: [invite] }} busyId={busyId} onRemove={() => undefined} onResend={(item) => sent.push(item)} /></I18nextProvider>));
  };
  try {
    await render(null);
    assert.ok(host.textContent?.includes("La invitación a contadora@example.test venció."));
    assert.equal(sent.length, 0);
    const resend = Array.from(host.querySelectorAll("button")).find((button) => button.textContent === "Reenviar");
    assert.ok(resend);
    await act(async () => resend.click());
    assert.deepEqual(sent, [invite]);
    await render(invite.id);
    assert.equal(resend.disabled, true);
    await act(async () => resend.click());
    assert.equal(sent.length, 1);
  } finally {
    await act(async () => root.unmount()); host.remove();
  }
});
