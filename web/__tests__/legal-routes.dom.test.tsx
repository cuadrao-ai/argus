import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

const ENV_NAMES = ["NEXT_PUBLIC_CUADRAO_TERMS_URL", "NEXT_PUBLIC_CUADRAO_PRIVACY_URL"] as const;

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});
afterEach(() => {
  for (const name of ENV_NAMES) delete process.env[name];
  window.localStorage.clear();
});

async function redirectedTo(route: "terms" | "privacy"): Promise<string> {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: Page } = route === "terms" ? await import("@/app/terms/page") : await import("@/app/privacy/page");
  const targets: string[] = [];
  const original = window.location.replace;
  window.location.replace = (url: string | URL) => void targets.push(String(url));
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    await act(async () => root.render(<Page />));
  } finally {
    await act(async () => root.unmount());
    window.location.replace = original;
  }
  assert.equal(targets.length, 1, `${route} replaced the location once`);
  return targets[0]!;
}

describe("the app's /terms and /privacy send readers to the published page in the app's language", () => {
  test("a device that last showed English opens the English pages", async () => {
    window.localStorage.setItem("i18nextLng", "en");
    assert.equal(await redirectedTo("terms"), "https://cuadrao.ai/en/app/terms");
    assert.equal(await redirectedTo("privacy"), "https://cuadrao.ai/en/app/privacy");
  });

  test("a device that last showed Spanish opens the Spanish pages when Spanish ships", async () => {
    const { SPANISH_ENABLED } = await import("@/lib/language-features");
    window.localStorage.setItem("i18nextLng", "es-419");
    const prefix = SPANISH_ENABLED ? "https://cuadrao.ai/app" : "https://cuadrao.ai/en/app";
    assert.equal(await redirectedTo("terms"), `${prefix}/${SPANISH_ENABLED ? "terminos" : "terms"}`);
    assert.equal(await redirectedTo("privacy"), `${prefix}/${SPANISH_ENABLED ? "privacidad" : "privacy"}`);
  });

  test("a set URL wins over the published one in every language", async () => {
    process.env.NEXT_PUBLIC_CUADRAO_TERMS_URL = "https://cuadrao.example/terminos";
    process.env.NEXT_PUBLIC_CUADRAO_PRIVACY_URL = " ";
    window.localStorage.setItem("i18nextLng", "en");
    assert.equal(await redirectedTo("terms"), "https://cuadrao.example/terminos");
    assert.equal(await redirectedTo("privacy"), "https://cuadrao.ai/en/app/privacy");
  });
});
