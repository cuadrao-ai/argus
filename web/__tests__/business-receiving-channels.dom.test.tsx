import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessWorkspaceInfo } from "@/lib/business-api";

let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const original = { node: process.env.NODE_ENV, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  document.body.innerHTML = "";
  window.history.replaceState(null, "", "/biz");
  if (original.node === undefined) Reflect.deleteProperty(process.env, "NODE_ENV"); else Reflect.set(process.env, "NODE_ENV", original.node);
  if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

type Source = ReturnType<typeof import("@/components/business-app/fixture-data").createFixtureBusinessDataSource>;

/** Mounts the real provider with the server workspace answer under test control. */
async function mount(answer: { available: boolean } | "hold", url = "/biz", overrides: Partial<Source> = {}, history = false) {
  search = url.includes("?") ? url.slice(url.indexOf("?")) : "";
  window.history.replaceState(null, "", url);
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { default: ReceiptSourcePreview } = await import("@/components/business-app/ReceiptSourcePreview");
  const { EmailRecord } = await import("@/components/business-app/BusinessEmailDeliveries");
  const { default: BusinessReception } = await import("@/components/business-app/BusinessReception");
  const { useForwardAddress } = await import("@/components/business-app/useForwardAddress");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  Reflect.set(process.env, "NODE_ENV", "development");
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  let release: ((workspace: BusinessWorkspaceInfo) => void) | null = null;
  const source = {
    ...fixture,
    workspace: async (): Promise<BusinessWorkspaceInfo> => {
      const workspace = await fixture.workspace();
      if (answer === "hold") return new Promise((resolve) => { release = resolve; });
      return { ...workspace, receiving_channels: { email: { available: answer.available }, whatsapp: { available: answer.available } } };
    },
    ...overrides,
  };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    const address = useForwardAddress();
    return <><p data-testid="forward-address">{address}</p>{history ? api.panel.kind === "email" ? <EmailRecord emailId={api.panel.emailId} /> : <ReceiptSourcePreview detail={{ id: "historical-receipt", media_type: "application/pdf", filename: "recibo.pdf", received_at: "2026-11-04T00:00:00Z", channel: "email", email_delivery_ids: ["historical-email", "historical-repeat"] }} /> : null}</>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never} userId="user-1">
            <Probe />
            <BusinessReception />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 40 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(done(), "the provider never settled");
  };
  // A held workspace answer holds the whole first load, so that case waits on the directory alone; a failed read settles on its error.
  await settle(() => api !== null && (answer === "hold" ? api.spaces !== null : api.records.inbox !== null || api.records.error));
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const text = () => host.textContent ?? "";
  return {
    act, host, settle, text,
    api: () => api!,
    // Waits for the read in flight to hold before answering it, so a reload's fresh read is the one released.
    release: async (workspace: Partial<BusinessWorkspaceInfo>) => {
      await settle(() => release !== null);
      const answer = release!;
      release = null;
      await act(async () => { answer({ ...(await fixture.workspace()), ...workspace }); });
    },
  };
}


test("off and unanswered channels expose no email offer or address request but retain history reads", async () => {
  for (const answer of [{ available: false }, "hold"] as const) {
    let addressRequests = 0;
    let deliveryRequests = 0;
    const page = await mount(answer, "/biz", {
      emailIntake: async () => { addressRequests += 1; return { enabled: true, receiving_address: "inbox@cuadrao.example" }; },
      emailDeliveries: async () => { deliveryRequests += 1; return []; },
    });
    assert.equal(addressRequests, 0);
    assert.ok(deliveryRequests > 0, "stored email history still loads");
    assert.equal(page.host.querySelector('[data-testid="email-address"]'), null);
    assert.ok(!page.text().includes("Remitentes"));
    assert.equal(page.host.querySelector('[data-testid="forward-address"]')?.textContent, "");
  }
});

test("available email without an address offers setup, independently of address activation", async () => {
  const page = await mount({ available: true }, "/biz", {
    emailIntake: async () => ({ enabled: false, receiving_address: null }),
    emailDeliveries: async () => [],
  });
  await page.settle(() => page.text().includes("Obtener una dirección"));
  assert.ok(page.text().includes("Remitentes"));
});

test("a Business switch drops channel capabilities and the old forwarding address before the next workspace answer", async () => {
  let addressRequests = 0;
  let deliveryRequests = 0;
  const page = await mount("hold", "/biz", {
    emailIntake: async () => { addressRequests += 1; return { enabled: true, receiving_address: "inbox@cuadrao.example" }; },
    emailDeliveries: async () => { deliveryRequests += 1; return []; },
  });
  await page.release({ receiving_channels: { email: { available: true }, whatsapp: { available: true } } });
  await page.settle(() => page.host.querySelector('[data-testid="forward-address"]')?.textContent === "inbox@cuadrao.example");
  const before = { addressRequests, deliveryRequests };
  const other = page.api().spaces?.find(space => space.grant_id !== page.api().chosen?.grant_id);
  assert.ok(other, "the fixture offers another Business");
  await page.act(async () => page.api().chooseBusiness(other!.grant_id));
  assert.equal(page.host.querySelector('[data-testid="forward-address"]')?.textContent, "");
  assert.equal(page.host.querySelector('[data-testid="email-address"]'), null);
  assert.equal(addressRequests, before.addressRequests);
  assert.ok(deliveryRequests > before.deliveryRequests, "the new Business loads its own stored history");
});


test("automatic grant fallback waits for the new Business workspace before intake requests", async () => {
  const { setChosenGrant } = await import("@/lib/business-grant");
  let requests = 0;
  const page = await mount("hold", "/biz", {
    emailIntake: async () => { requests += 1; return { enabled: true, receiving_address: "inbox@cuadrao.example" }; },
    emailDeliveries: async () => [],
  });
  const enabled = { receiving_channels: { email: { available: true }, whatsapp: { available: true } } };
  await page.release(enabled);
  const other = page.api().spaces?.find(space => space.role === "accountant");
  assert.ok(other);
  await page.act(async () => page.api().chooseBusiness(other!.grant_id));
  await page.release(enabled);
  await page.settle(() => page.host.querySelector('[data-testid="forward-address"]')?.textContent === "inbox@cuadrao.example");
  const before = requests;
  // Directory removal and grant refusal both use this automatic fallback path.
  await page.act(async () => setChosenGrant(null));
  assert.equal(page.api().receivingChannels?.email.available, false);
  assert.equal(page.host.querySelector('[data-testid="forward-address"]')?.textContent, "");
  assert.equal(requests, before);
});


test("email off: Ver correo opens the stored email and body while intake and retry stay unavailable", async () => {
  let listReads = 0;
  let bodyReads = 0;
  let intakeRequests = 0;
  let retryRequests = 0;
  const delivery = { id: "historical-email", state: "captured" as const, received_at: "2026-11-04T00:00:00Z", updated_at: "2026-11-04T00:00:00Z", sender: "sender@cuadrao.example", subject: "Recibo guardado", sent_at: null, error_code: null, retryable: true, original_document_id: null, parts: [{ id: "part", filename: "recibo.pdf", media_type: "application/pdf", state: "captured" as const, document_id: "historical-receipt", error_code: null }] };
  const page = await mount({ available: false }, "/biz", {
    emailDeliveries: async () => { listReads += 1; return [delivery]; },
    emailDelivery: async () => { bodyReads += 1; return { ...delivery, text_body: "Mensaje histórico conservado" }; },
    emailIntake: async () => { intakeRequests += 1; return { enabled: false, receiving_address: null }; },
    retryEmailDelivery: async () => { retryRequests += 1; return { id: delivery.id }; },
    receiptSource: () => new Promise<Blob>(() => undefined),
  }, true);
  assert.ok(listReads > 0);
  assert.equal(page.api().records.emails?.length, 1);
  assert.ok(page.text().includes("Llegó por correo"));
  assert.ok(page.text().includes("Este archivo llegó 2 veces por correo."));
  const seeEmail = page.host.querySelector<HTMLButtonElement>('[data-testid="receipt-see-email"]');
  assert.ok(seeEmail);
  await page.act(async () => seeEmail!.click());
  await page.settle(() => page.text().includes("Mensaje histórico conservado"));
  assert.ok(page.host.querySelector('[data-testid="email-record"]'));
  assert.ok(page.text().includes("Recibo guardado"));
  assert.ok(page.text().includes("recibo.pdf"));
  assert.equal(bodyReads, 1);
  assert.equal(intakeRequests, 0);
  assert.equal(retryRequests, 0);
  assert.ok(!page.text().includes("Obtener una dirección"));
  const retryLabel = (await import("@/public/locales/es-419/common.json")).default.business.email.retry;
  assert.ok(![...page.host.querySelectorAll("button")].some(button => button.textContent === retryLabel));
});
