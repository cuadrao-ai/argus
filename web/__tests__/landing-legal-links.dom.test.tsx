import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import type { Root } from "react-dom/client";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

mock.module("next/navigation", () => ({
  useRouter: () => ({ push: () => undefined, replace: () => undefined, refresh: () => undefined }),
  useSearchParams: () => new URLSearchParams(),
}));

const mounted = new Map<Root, HTMLElement>();
let restoreFetch: (() => void) | null = null;

const ENV_NAMES = [
  "NEXT_PUBLIC_CUADRAO_TERMS_URL",
  "NEXT_PUBLIC_CUADRAO_PRIVACY_URL",
  "NEXT_PUBLIC_CUADRAO_DATA_DELETION_URL",
] as const;
const TERMS = "https://cuadrao.example/terminos";
const PRIVACY = "https://cuadrao.example/privacidad";
const PUBLISHED_TERMS = "https://cuadrao.ai/terminos";
const PUBLISHED_PRIVACY = "https://cuadrao.ai/privacidad";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});
afterEach(async () => {
  const { act } = await import("react");
  await act(async () => { for (const [root, host] of mounted) { root.unmount(); host.remove(); } });
  mounted.clear();
  restoreFetch?.();
  restoreFetch = null;
  for (const name of ENV_NAMES) delete process.env[name];
});

async function mountFrontDoor(query: string) {
  window.history.replaceState(null, "", `/${query}`);
  const originalFetch = globalThis.fetch;
  restoreFetch = () => { globalThis.fetch = originalFetch; };
  globalThis.fetch = async () => Response.json({ code: "profile_unavailable" }, { status: 503 });
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
  mounted.set(root, host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <LandingPage />
      </I18nextProvider>,
    );
  });
  await act(async () => {
    if (host.querySelector("[data-auth-brand]")) return;
    await new Promise<void>((resolve, reject) => {
      const observer = new MutationObserver(() => {
        if (!host.querySelector("[data-auth-brand]")) return;
        observer.disconnect(); clearTimeout(timeout); resolve();
      });
      const timeout = setTimeout(() => { observer.disconnect(); reject(new Error("Front door did not settle")); }, 1000);
      observer.observe(host, { childList: true, subtree: true });
    });
  });
  return { act, root: { unmount: () => { root.unmount(); mounted.delete(root); host.remove(); } }, host };
}

const SURFACES = [
  ["intro", ""],
  ["login", "?auth=login"],
  ["signup", "?auth=signup"],
] as const;

describe("the signed-out front door legal links", () => {
  for (const [name, query] of SURFACES) {
    test(`${name}: no /terms or /privacy link, only the Cuadrao pages`, async () => {
      const page = await mountFrontDoor(query);
      assert.ok(page.host.querySelector("[data-auth-brand]"), "the front door rendered");
      assert.equal(page.host.querySelector('a[href="/terms"], a[href="/privacy"]'), null);
      for (const link of page.host.querySelectorAll("a[href^='http']")) {
        assert.ok([PUBLISHED_TERMS, PUBLISHED_PRIVACY].includes(link.getAttribute("href")!), link.getAttribute("href")!);
      }
      await page.act(async () => page.root.unmount());
    });
  }

  test("intro: with nothing set, the sentence links the published pages", async () => {
    const page = await mountFrontDoor("");
    const links = [...page.host.querySelectorAll("a")];
    assert.deepEqual(links.map((link) => link.getAttribute("href")), [PUBLISHED_TERMS, PUBLISHED_PRIVACY]);
    assert.match(links[0]!.parentElement!.textContent!, /^Al registrarte, aceptas nuestros .+ y .+\.$/);
    await page.act(async () => page.root.unmount());
  });

  test("intro: set URLs replace the published ones", async () => {
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
