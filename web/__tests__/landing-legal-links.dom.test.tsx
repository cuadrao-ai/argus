import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

mock.module("next/navigation", () => ({
  useRouter: () => ({ push: () => undefined, replace: () => undefined, refresh: () => undefined }),
  useSearchParams: () => new URLSearchParams(),
}));

const ENV_NAMES = [
  "NEXT_PUBLIC_CUADRAO_TERMS_URL",
  "NEXT_PUBLIC_CUADRAO_PRIVACY_URL",
  "NEXT_PUBLIC_CUADRAO_DATA_DELETION_URL",
] as const;
const TERMS = "https://cuadrao.example/terminos";
const PRIVACY = "https://cuadrao.example/privacidad";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});
afterEach(() => {
  for (const name of ENV_NAMES) delete process.env[name];
});

async function mountFrontDoor(query: string) {
  window.history.replaceState(null, "", `/${query}`);
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: LandingPage } = await import("@/app/page");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <LandingPage />
      </I18nextProvider>,
    );
  });
  for (let turn = 0; turn < 5; turn += 1) await act(async () => { await Promise.resolve(); });
  return { act, root, host };
}

const SURFACES = [
  ["intro", ""],
  ["login", "?auth=login"],
  ["signup", "?auth=signup"],
] as const;

describe("the signed-out front door legal links", () => {
  for (const [name, query] of SURFACES) {
    test(`${name}: no /terms or /privacy link and no acceptance sentence while the Cuadrao URLs are unpublished`, async () => {
      const page = await mountFrontDoor(query);
      assert.ok(page.host.querySelector("[data-auth-brand]"), "the front door rendered");
      assert.equal(page.host.querySelector('a[href="/terms"], a[href="/privacy"]'), null);
      assert.ok(!page.host.textContent!.includes("aceptas nuestros"));
      await page.act(async () => page.root.unmount());
    });

    test(`${name}: one published URL renders no acceptance sentence`, async () => {
      process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = PRIVACY;
      const page = await mountFrontDoor(query);
      assert.ok(page.host.querySelector("[data-auth-brand]"), "the front door rendered");
      assert.equal(page.host.querySelector('a[href^="https://cuadrao.example"]'), null);
      assert.ok(!page.host.textContent!.includes("aceptas nuestros"));
      await page.act(async () => page.root.unmount());
    });
  }

  test("intro: both URLs published render the base sentence linking to them", async () => {
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = TERMS;
    process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = PRIVACY;
    const page = await mountFrontDoor("");
    const links = [...page.host.querySelectorAll("a")];
    assert.deepEqual(links.map((link) => link.getAttribute("href")), [TERMS, PRIVACY]);
    const sentence = links[0]!.parentElement!;
    assert.match(sentence.textContent!, /^Al registrarte, aceptas nuestros .+ y .+\.$/);
    await page.act(async () => page.root.unmount());
  });
});
