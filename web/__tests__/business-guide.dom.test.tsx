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

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => { await GlobalRegistrator.unregister(); });

type GuideRequest = { method: string; url: string; signal: AbortSignal | null | undefined; finish: (response: Response) => void };

async function mount() {
  const originalFetch = globalThis.fetch;
  const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const requests: GuideRequest[] = [];
  globalThis.fetch = (url, init) => new Promise<Response>(finish => {
    requests.push({ method: init?.method ?? "GET", url: String(url), signal: init?.signal, finish });
  });
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const render = async (userId = "ana") => {
    await act(async () => root.render(
      <I18nextProvider i18n={i18n}>
        <GuideCard cardId="bandeja-intro" userId={userId} title="Del documento al registro"
          points={[
            { label: "Sube tus documentos", body: "Agrega fotos o PDF." },
            { label: "Revisa y aprueba", body: "El documento pasa a Registros." },
            { label: "Retoma lo pendiente", body: "Vuelve a la revisión." },
          ]}
        />
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
    guide: () => host.querySelector("section"),
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
const state = (dismissed: boolean) => Response.json({ dismissed });

test("the guide waits for the read and hides only after a confirmed save", async () => {
  const page = await mount();
  try {
    assert.equal(page.guide(), null);
    assert.equal(page.alert(), null);
    assert.equal(page.requests[0]?.method, "GET");
    assert.ok(page.requests[0]?.url.endsWith("/business/guide-cards/bandeja-intro"));
    await page.finish(0, state(false));
    assert.equal(page.guide()?.querySelector("h3")?.textContent, "Del documento al registro");
    assert.deepEqual(
      [...page.host.querySelectorAll("li strong")].map(item => item.textContent),
      ["Sube tus documentos", "Revisa y aprueba", "Retoma lo pendiente"],
    );
    await act(async () => page.button("Ocultar guía").click());
    assert.equal(page.button("Ocultar guía").disabled, true);
    assert.equal(page.requests[1]?.method, "POST");
    assert.ok(page.requests[1]?.url.endsWith("/business/guide-cards/bandeja-intro/dismiss"));
    await page.finish(1, state(true));
    assert.equal(page.guide(), null);
    assert.equal(localStorage.length, 0);
    assert.equal(sessionStorage.length, 0);
  } finally { await page.close(); }
});

test("read and save failures offer a retry without inventing guide state", async () => {
  const page = await mount();
  try {
    await page.finish(0, unavailable());
    assert.equal(page.guide(), null);
    assert.equal(page.alert()?.querySelector('[title="guide-server-123"]')?.getAttribute("title"), "guide-server-123");
    await act(async () => page.button("Reintentar").click());
    await page.finish(1, state(false));
    await act(async () => page.button("Ocultar guía").click());
    await page.finish(2, state(false));
    assert.ok(page.guide());
    assert.ok(page.alert());
    assert.equal(page.alert()?.querySelector("[data-reference-short]"), null);
    await act(async () => page.button("Reintentar").click());
    await page.finish(3, unavailable());
    assert.ok(page.guide());
    assert.ok(page.alert()?.querySelector('[title="guide-server-123"]'));
    await act(async () => page.button("Reintentar").click());
    await page.finish(4, state(true));
    assert.equal(page.guide(), null);
  } finally { await page.close(); }
});

test("an earlier person's read or save cannot change a new person's guide", async () => {
  const page = await mount();
  try {
    await page.render("beto");
    assert.equal(page.requests[0]?.signal?.aborted, true);
    await page.finish(0, state(false));
    assert.equal(page.guide(), null);
    await page.finish(1, state(false));
    assert.ok(page.guide());
    await act(async () => page.button("Ocultar guía").click());
    await page.render("carla");
    assert.equal(page.requests[2]?.signal?.aborted, true);
    await page.finish(3, state(false));
    await page.finish(2, state(true));
    assert.ok(page.guide());
    await page.render("beto");
    assert.equal(page.guide(), null);
    await page.finish(4, state(true));
    assert.equal(page.guide(), null);
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
  for (const path of ["/api/v1/business/guide-cards/{card_id}", "/api/v1/business/guide-cards/{card_id}/dismiss"]) {
    assert.deepEqual([...BUSINESS_GUIDE_CARD_IDS].sort(), openApiCardIds(path).sort(), path);
  }
});
