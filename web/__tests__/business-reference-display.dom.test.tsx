import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

// A server request id is a full UUID. Every reference a person reads is its
// short form; the full id stays in the title, the accessible name and the copy.
const REQUEST_ID = "4ea79978-ce17-4853-b232-b2a72f4c9ce7";
const SHORT = "Ref. 4ea79978";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 800, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function render(node: (deps: { ServerErrorScreen: typeof import("@/components/status/ServerErrorScreen").ServerErrorScreen; BusinessConsentScreen: typeof import("@/components/business-app/BusinessConsentScreen").BusinessConsentScreen }) => React.ReactNode) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { ServerErrorScreen } = await import("@/components/status/ServerErrorScreen");
  const { BusinessConsentScreen } = await import("@/components/business-app/BusinessConsentScreen");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}>{node({ ServerErrorScreen, BusinessConsentScreen })}</I18nextProvider>);
  });
  return { host, unmount: () => act(async () => { root.unmount(); host.remove(); }) };
}

function assertShortReference(host: HTMLElement, where: string) {
  const references = [...host.querySelectorAll<HTMLElement>('[data-testid="error-reference"]')];
  assert.equal(references.length, 1, `${where} shows one reference`);
  const [reference] = references;
  assert.equal(reference.querySelector("[data-reference-short]")?.textContent, SHORT, `${where} reads the short form`);
  assert.equal(reference.title, REQUEST_ID, `${where} keeps the full id in its title`);
  const shown = reference.cloneNode(true) as HTMLElement;
  for (const hidden of shown.querySelectorAll(".sr-only")) hidden.remove();
  assert.equal(shown.textContent?.trim(), SHORT, `${where} shows nothing longer than the short form`);
  assert.ok(reference.textContent?.includes(REQUEST_ID), `${where} names the full id to a screen reader`);
}

test("the full-page server error reads the short reference", async () => {
  const page = await render(({ ServerErrorScreen }) => <ServerErrorScreen reference={REQUEST_ID} onRetry={() => undefined} />);
  assertShortReference(page.host, "the server error screen");
  await page.unmount();
});

test("the consent save failure reads the short reference", async () => {
  const page = await render(({ BusinessConsentScreen }) => <BusinessConsentScreen save={{ kind: "failed", reference: REQUEST_ID }} onContinue={() => undefined} />);
  assertShortReference(page.host, "the consent failure");
  await page.unmount();
});

// Files that still print a reference through their own copy key. Each is
// held by another lane and switches to ReferenceCode there; the list only shrinks.
const NOT_YET_SWITCHED = new Set<string>();

test("no screen prints a reference except through ReferenceCode", () => {
  const root = join(import.meta.dir, "..");
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(join(root, dir))) {
      const path = join(dir, name);
      if (statSync(join(root, path)).isDirectory()) walk(path);
      else if (path.endsWith(".tsx")) files.push(path);
    }
  };
  walk("components");
  walk("app");
  const printing = files.filter((path) => /\bt\(\s*"[^"]*\.reference"\s*,\s*\{\s*reference\b/.test(readFileSync(join(root, path), "utf8")));
  const offenders = printing.filter((path) => !path.endsWith("components/status/ReferenceCode.tsx") && !NOT_YET_SWITCHED.has(path));
  assert.deepEqual(offenders, []);
});

test("the two copy keys that printed a reference on their own are gone in both languages", () => {
  const root = join(import.meta.dir, "..");
  for (const language of ["es-419", "en"]) {
    const catalog = JSON.parse(readFileSync(join(root, "public/locales", language, "common.json"), "utf8"));
    assert.equal(catalog.business.consent.reference, undefined, `${language} business.consent.reference`);
    assert.equal(catalog.business.transactions.error.reference, undefined, `${language} business.transactions.error.reference`);
    assert.equal(catalog.common.reference, "Ref. {{reference}}", `${language} keeps the one key ReferenceCode reads`);
  }
});
