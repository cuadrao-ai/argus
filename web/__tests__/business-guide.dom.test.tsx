import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { readFileSync } from "node:fs";
import GuideCard from "@/components/business-app/foundation/GuideCard";
import { BUSINESS_GUIDE_CARD_IDS } from "@/lib/business-guide-api";
import { ShellAccount } from "./support/shell-account";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => { await GlobalRegistrator.unregister(); });

type GuideRequest = { method: string; url: string; finish: (response: Response) => void };
type Start = { member?: string | null; dismissed?: string[] | null; pending?: boolean };

async function mount(start: Start = {}) {
  const originalFetch = globalThis.fetch;
  const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const requests: GuideRequest[] = [];
  globalThis.fetch = (url, init) => new Promise<Response>(finish => {
    requests.push({ method: init?.method ?? "GET", url: String(url), finish });
  });
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = async ({ member = "ana", dismissed = [], pending = false }: Start = start) => {
    await act(async () => root.render(
      <I18nextProvider i18n={i18n}>
        <ShellAccount member={member} dismissed={dismissed}>
          <GuideCard cardId="bandeja-intro" pending={pending} title="Del documento al registro"
            points={[
              { label: "Sube tus documentos", body: "Agrega fotos o PDF." },
              { label: "Revisa y aprueba", body: "El documento pasa a Registros." },
              { label: "Retoma lo pendiente", body: "Vuelve a la revisión." },
            ]}
          />
        </ShellAccount>
      </I18nextProvider>,
    ));
  };
  const button = (label: string) => {
    const match = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
      item => item.textContent === label || item.getAttribute("aria-label") === label,
    );
    assert.ok(match, label);
    return match;
  };
  await render();
  return {
    render, host, requests, button,
    guide: () => host.querySelector("section[aria-labelledby]"),
    alert: () => host.querySelector('[role="alert"]'),
    finish: async (index: number, response: Response) => {
      const request = requests[index];
      assert.ok(request, `request ${index}`);
      await act(async () => request.finish(response));
    },
    close: async () => {
      await act(async () => root.unmount());
      host.remove();
      globalThis.fetch = originalFetch;
      if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
      else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock;
    },
  };
}

const unavailable = () => Response.json({}, { status: 503, headers: { "X-Request-Id": "guide-server-123" } });
const saved = () => Response.json({ dismissed: true });

test("the guide draws from the account without a read, hides at once on dismiss and saves once", async () => {
  const page = await mount();
  try {
    assert.equal(page.guide()?.querySelector("h3")?.textContent, "Del documento al registro");
    assert.deepEqual(
      [...page.host.querySelectorAll("li strong")].map(item => item.textContent),
      ["Sube tus documentos", "Revisa y aprueba", "Retoma lo pendiente"],
    );
    assert.equal(page.requests.length, 0, "no guide read");
    await act(async () => page.button("Ocultar guía").click());
    assert.equal(page.guide(), null, "the guide leaves at once");
    assert.deepEqual(page.requests.map(request => request.method), ["POST"]);
    assert.ok(page.requests[0]?.url.endsWith("/business/guide-cards/bandeja-intro/dismiss"));
    await page.finish(0, saved());
    assert.equal(page.guide(), null);
    assert.equal(page.requests.length, 1);
    assert.equal(localStorage.length, 0);
    assert.equal(sessionStorage.length, 0);
  } finally { await page.close(); }
});

test("a refused save brings the guide back with its reference and retry", async () => {
  const page = await mount();
  try {
    await act(async () => page.button("Ocultar guía").click());
    await page.finish(0, unavailable());
    assert.ok(page.guide());
    assert.equal(page.alert()?.querySelector('[title="guide-server-123"]')?.getAttribute("title"), "guide-server-123");
    await act(async () => page.button("Reintentar").click());
    assert.equal(page.guide(), null);
    await page.finish(1, saved());
    assert.equal(page.guide(), null);
    assert.deepEqual(page.requests.map(request => request.method), ["POST", "POST"]);
  } finally { await page.close(); }
});

test("a dismissed or unknown guide draws nothing and asks nothing", async () => {
  for (const start of [{ dismissed: ["bandeja-intro"] }, { dismissed: null }, { member: null }]) {
    const page = await mount(start);
    try {
      assert.equal(page.host.childElementCount, 0, JSON.stringify(start));
      await page.render({ ...start, pending: true });
      assert.equal(page.host.childElementCount, 0, "no place either");
      assert.equal(page.requests.length, 0);
    } finally { await page.close(); }
  }
});

test("pending, the guide holds its place with nothing in it, then draws in the same element", async () => {
  const page = await mount({ pending: true });
  try {
    const place = page.host.querySelector("section");
    assert.ok(place?.hasAttribute("data-guide-slot"));
    assert.equal(place.getAttribute("aria-hidden"), "true");
    assert.equal(page.guide(), null);
    assert.ok([...place.children].every(child => (child as HTMLElement).style.visibility === "hidden"));
    await page.render({ pending: false });
    assert.equal(page.host.querySelector("section"), place, "the guide takes the place's element");
    assert.equal(page.guide(), place);
    assert.ok([...place.children].every(child => (child as HTMLElement).style.visibility === ""));
    assert.equal(page.requests.length, 0);
  } finally { await page.close(); }
});

test("an earlier person's refused save cannot change a new person's guide", async () => {
  const page = await mount();
  try {
    await act(async () => page.button("Ocultar guía").click());
    await page.render({ member: "beto", dismissed: ["bandeja-intro"] });
    assert.equal(page.guide(), null, "beto dismissed it before");
    await page.finish(0, unavailable());
    assert.equal(page.guide(), null, "ana's refused save does not bring back beto's guide");
    assert.equal(page.alert(), null);
  } finally { await page.close(); }
});

/** The `card_id` enum the checked OpenAPI artifact declares under one guide-card path. */
function openApiCardIds(path: string): string[] {
  const lines = readFileSync(new URL("../../docs/api/openapi.yaml", import.meta.url), "utf8").split("\n");
  const start = lines.indexOf(`  ${path}:`);
  assert.ok(start >= 0, path);
  const values: string[] = [];
  for (const line of lines.slice(lines.indexOf("          enum:", start) + 1)) {
    const value = line.match(/^ {10}- ([a-z0-9-]+)$/);
    if (!value) break;
    values.push(value[1]);
  }
  return values;
}

test("the web knows exactly the guide card IDs the server declares", () => {
  assert.deepEqual([...BUSINESS_GUIDE_CARD_IDS].sort(), openApiCardIds("/api/v1/business/guide-cards/{card_id}/dismiss").sort());
});
