import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { EmailReadingView } from "../components/settings/EmailReadingPanel";
import { EmailReceivingAddress } from "../components/business-app/BusinessEmailDeliveries";
import type { BusinessEmailAIReading, BusinessEmailIntake } from "../lib/business-email";
import { canAgreeToReading, emailReadingProblem, readingModels, toggleEmailReading, type EmailReadingClient } from "../lib/business-email-consent-api";

const reading = (over: Partial<BusinessEmailAIReading> = {}): BusinessEmailAIReading => ({
  state: "unseen",
  available: true,
  reason: null,
  owner: true,
  scope_version: 1,
  purpose: "business_email_receipt_reading",
  disclosure: "Cuadrao leerá con IA los recibos que lleguen a esta dirección. Los correos reenviados pueden incluir datos de otras personas; los adjuntos se envían a OpenRouter y al modelo indicado abajo. Puedes apagarlo en Ajustes.",
  route: { gateway: "openrouter", interpretation: [{ model: "vision-fixture" }], reply: [] },
  disclosure_token: "a".repeat(64),
  consented_at: null,
  consented_by: null,
  revoked_at: null,
  ...over,
});

async function i18n(lng: "es-419" | "en") {
  const instance = i18next.createInstance();
  await instance.init({ lng, fallbackLng: false, resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  return instance;
}

async function address(intake: BusinessEmailIntake, lng: "es-419" | "en" = "es-419") {
  return renderToStaticMarkup(
    <I18nextProvider i18n={await i18n(lng)}>
      <EmailReceivingAddress intake={intake} onActivate={async () => undefined} />
    </I18nextProvider>,
  );
}

describe("the address screen says in one line that emailed receipts are read with AI", () => {
  test("the owner sees the server's disclosure and the provider and model before asking for an address", async () => {
    const html = await address({ enabled: false, receiving_address: null, ai_reading: reading() });
    assert.ok(html.includes('data-testid="email-reading-line"'));
    assert.ok(html.includes("los adjuntos se envían a OpenRouter y al modelo indicado abajo"));
    assert.ok(html.includes("Proveedor: OpenRouter. Modelo: vision-fixture."));
    assert.ok(html.includes("Obtener una dirección"));
    assert.ok(!html.includes("—"));
  });

  test("someone who is not the owner asks for the address without the line; sample data carries no line at all", async () => {
    const grantee = await address({ enabled: false, receiving_address: null, ai_reading: reading({ owner: false, available: false, reason: "business_owner_required", disclosure_token: null }) });
    assert.ok(!grantee.includes("email-reading-line"));
    assert.ok(!(await address({ enabled: false, receiving_address: null })).includes("email-reading-line"));
  });

  test("with an address the state reads on, off, or waiting for the owner; an owner's unanswered notice is the banner's, not a line", async () => {
    const base = { enabled: true, receiving_address: "recibos-7f3a9c21@recibos.cuadrao.example" };
    const on = await address({ ...base, ai_reading: reading({ state: "on" }) });
    assert.ok(on.includes('data-state="on"') && on.includes("Lectura con IA: activada.") && on.includes("Cambiar en Ajustes"));
    const off = await address({ ...base, ai_reading: reading({ state: "off" }) });
    assert.ok(off.includes("Lectura con IA: apagada. Los recibos quedan guardados, sin leer."));
    const pending = await address({ ...base, ai_reading: reading({ state: "unseen", owner: false, available: false, disclosure_token: null }) });
    assert.ok(pending.includes("pendiente de la decisión del dueño") && !pending.includes("Cambiar en Ajustes"));
    const unseenOwner = await address({ ...base, ai_reading: reading({ state: "unseen" }) });
    assert.ok(!unseenOwner.includes("email-reading-state"));
    const english = await address({ ...base, ai_reading: reading({ state: "on" }) }, "en");
    assert.ok(english.includes("AI reading: on.") && english.includes("Change in Settings"));
  });
});

describe("the settings panel's one switch", () => {
  async function view(props: Partial<Parameters<typeof EmailReadingView>[0]>, lng: "es-419" | "en" = "es-419") {
    return renderToStaticMarkup(
      <I18nextProvider i18n={await i18n(lng)}>
        <EmailReadingView intake={null} loading={false} busy={false} problem={null} onToggle={() => undefined} {...props} />
      </I18nextProvider>,
    );
  }

  test("shows the disclosure verbatim, names the provider and the model, and says who turned it on and when", async () => {
    const html = await view({ intake: { enabled: true, receiving_address: "recibos-1@x.test", ai_reading: reading({ state: "on", consented_at: "2026-10-13T20:00:00Z", consented_by: "Lía" }) } });
    assert.ok(html.includes("Leer con IA los recibos que lleguen por correo"));
    assert.ok(html.includes("Puedes apagarlo en Ajustes."));
    assert.ok(html.includes("Proveedor: OpenRouter. Modelo: vision-fixture."));
    assert.ok(html.includes("por Lía"));
    assert.ok(html.includes('aria-checked="true"') || html.includes('checked=""'));
    assert.ok(html.includes("recibos-1@x.test"));
  });

  test("a person who is not the owner reads the state and cannot move the switch", async () => {
    const html = await view({ intake: { enabled: true, receiving_address: "recibos-1@x.test", ai_reading: reading({ state: "on", owner: false, available: false, reason: "business_owner_required", disclosure_token: null }) } });
    assert.ok(html.includes("Solo el dueño del negocio puede cambiar esto."));
    assert.ok(/<button[^>]*role="switch"[^>]*disabled=""/.test(html) || /disabled=""[^>]*role="switch"/.test(html));
  });

  test("off and pending states read as such; a stale text or model says to read again", async () => {
    const off = await view({ intake: { enabled: true, receiving_address: "r@x.test", ai_reading: reading({ state: "off" }) } });
    assert.ok(off.includes("Apagado. Los recibos que lleguen quedan guardados, sin leer."));
    const pending = await view({ intake: { enabled: false, receiving_address: null, ai_reading: reading() }, problem: "stale" });
    assert.ok(pending.includes("Pendiente. Decide aquí o en la Bandeja."));
    assert.ok(pending.includes("El texto o el modelo cambiaron. Vuelve a leerlo y confirma."));
    assert.ok(pending.includes("Este negocio todavía no tiene dirección."));
  });
});

describe("the permission client", () => {
  test("models are named once; agreeing needs the owner, availability, a route and a signed token", () => {
    assert.deepEqual(readingModels(reading({ route: { gateway: "openrouter", interpretation: [{ model: "a" }, { model: "a" }], reply: [{ model: "b" }] } })), ["a", "b"]);
    assert.equal(canAgreeToReading(reading()), true);
    assert.equal(canAgreeToReading(reading({ owner: false })), false);
    assert.equal(canAgreeToReading(reading({ available: false })), false);
    assert.equal(canAgreeToReading(reading({ route: null })), false);
    assert.equal(canAgreeToReading(reading({ disclosure_token: "short" })), false);
    assert.equal(canAgreeToReading(null), false);
  });

  test("the switch turns on against the token shown and turns off with a revoke, keeping off when the re-read fails", async () => {
    const calls: string[] = [];
    const client: EmailReadingClient = {
      enable: async (token, key, language) => { calls.push(`enable:${token.slice(0, 4)}:${key}:${language}`); return reading({ state: "on" }); },
      decline: async () => reading({ state: "off" }),
      revoke: async () => { calls.push("revoke"); },
      read: async () => { throw new Error("offline"); },
      newKey: () => "key-1",
    };
    const on = await toggleEmailReading(reading(), client, "es-419");
    assert.equal(on.state, "on");
    const off = await toggleEmailReading(on, client, "es-419");
    assert.equal(off.state, "off");
    assert.deepEqual(calls, ["enable:aaaa:key-1:es-419", "revoke"]);
    await assert.rejects(toggleEmailReading(reading({ owner: false }), client));
  });

  test("problems map to what the screen can say", () => {
    assert.equal(emailReadingProblem({ status: 409, code: "email_consent_disclosure_stale" }), "stale");
    assert.equal(emailReadingProblem({ status: 403, code: "business_owner_required" }), "owner");
    assert.equal(emailReadingProblem({ status: 503, code: "email_ai_consent_unavailable" }), "unavailable");
    assert.equal(emailReadingProblem(new Error("x")), "failed");
  });
});
