import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessEmailAIReading } from "@/lib/business-email";

// A real DOM: the notice is answered by a tap on one of its two buttons and by
// nothing else; closing the page or scrolling creates nothing.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const reading = (over: Partial<BusinessEmailAIReading> = {}): BusinessEmailAIReading => ({
  state: "unseen",
  available: true,
  reason: null,
  owner: true,
  scope_version: 1,
  purpose: "business_email_receipt_reading",
  disclosure: "Cuadrao leerá con IA los recibos que lleguen a esta dirección.",
  route: { gateway: "openrouter", interpretation: [{ model: "vision-fixture" }], reply: [] },
  disclosure_token: "a".repeat(64),
  consented_at: null,
  consented_by: null,
  revoked_at: null,
  ...over,
});

async function mount(options: { reading?: BusinessEmailAIReading; fail?: boolean }) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { EmailReadingNotice } = await import("@/components/business-app/BusinessEmailDeliveries");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const answers: string[] = [];
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <EmailReadingNotice
          reading={options.reading ?? reading()}
          onAnswer={async (action) => {
            answers.push(action);
            if (options.fail) throw new Error("offline");
          }}
        />
      </I18nextProvider>,
    );
  });
  const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });
  await settle();
  return { act, root, host, answers, settle };
}

describe("the one-time notice for an address that existed before reading with AI", () => {
  test("is a labelled region with the sentence, the provider line and two side-by-side answers at least 44px tall", async () => {
    const page = await mount({});
    const region = page.host.querySelector('[data-testid="email-reading-notice"]')!;
    assert.equal(region.getAttribute("role"), "region");
    assert.equal(region.getAttribute("aria-labelledby"), "email-reading-notice-title");
    assert.ok(page.host.querySelector("#email-reading-notice-title")?.textContent?.length);
    assert.ok(region.textContent?.includes("Ahora leemos con IA los recibos que llegan por correo. El adjunto se envía a nuestro proveedor de IA y puede incluir datos de otras personas."));
    assert.ok(region.textContent?.includes("Proveedor: OpenRouter. Modelo: vision-fixture."));
    const understood = page.host.querySelector('[data-testid="email-reading-understood"]') as HTMLButtonElement;
    const turnOff = page.host.querySelector('[data-testid="email-reading-turn-off"]') as HTMLButtonElement;
    assert.equal(understood.textContent, "Entendido");
    assert.equal(turnOff.textContent, "Desactivar");
    assert.ok(understood.className.includes("min-h-11") && turnOff.className.includes("min-h-11"));
    assert.equal(region.querySelector('[aria-label*="errar"], [aria-label*="lose"]'), null, "no close control: closing is not an answer");
    // Focus is not taken by the notice.
    assert.equal(document.activeElement, document.body);
    assert.deepEqual(page.answers, []);
    await page.act(async () => page.root.unmount());
  });

  test("Entendido records the permission; Desactivar declines; each is one tap", async () => {
    const page = await mount({});
    const understood = page.host.querySelector('[data-testid="email-reading-understood"]') as HTMLButtonElement;
    await page.act(async () => { understood.click(); });
    await page.settle();
    assert.deepEqual(page.answers, ["enable"]);
    const turnOff = page.host.querySelector('[data-testid="email-reading-turn-off"]') as HTMLButtonElement;
    await page.act(async () => { turnOff.click(); });
    await page.settle();
    assert.deepEqual(page.answers, ["enable", "decline"]);
    await page.act(async () => page.root.unmount());
  });

  test("a failed answer says so and leaves both buttons for another try", async () => {
    const page = await mount({ fail: true });
    const understood = page.host.querySelector('[data-testid="email-reading-understood"]') as HTMLButtonElement;
    await page.act(async () => { understood.click(); });
    await page.settle();
    assert.ok(page.host.querySelector('[role="alert"]')?.textContent?.includes("No pudimos guardar tu respuesta."));
    assert.equal(understood.disabled, false);
    assert.equal((page.host.querySelector('[data-testid="email-reading-turn-off"]') as HTMLButtonElement).disabled, false);
    await page.act(async () => page.root.unmount());
  });

  test("without a token the agreement button cannot be pressed; the decline still can", async () => {
    const page = await mount({ reading: reading({ disclosure_token: null, available: false, reason: "email_ai_route_unavailable" }) });
    assert.equal((page.host.querySelector('[data-testid="email-reading-understood"]') as HTMLButtonElement).disabled, true);
    assert.equal((page.host.querySelector('[data-testid="email-reading-turn-off"]') as HTMLButtonElement).disabled, false);
    await page.act(async () => page.root.unmount());
  });
});
