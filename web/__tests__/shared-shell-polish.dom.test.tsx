import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { renderToStaticMarkup } from "react-dom/server";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const unmounts: Array<() => Promise<void>> = [];
afterEach(async () => {
  for (const unmount of unmounts.splice(0)) await unmount();
  // The overlay registry is a process-wide singleton: leave it not listening on this document.
  (await import("../components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});

async function i18nFor(lng: "en" | "es-419") {
  const i18n = createInstance();
  await i18n.init({
    lng,
    fallbackLng: false,
    resources: { en: { translation: en }, "es-419": { translation: es } },
  });
  return i18n;
}

describe("chat header heading", () => {
  test("renders no h1 when the shell has no title to show", async () => {
    const { ChatHeaderHeading } = await import("../components/chat/ChatInterface");
    const empty = renderToStaticMarkup(<ChatHeaderHeading>{false}</ChatHeaderHeading>);
    assert.equal(empty, "");
    assert.equal(renderToStaticMarkup(<ChatHeaderHeading>{null}</ChatHeaderHeading>), "");
  });

  test("keeps the heading when there is a title", async () => {
    const { ChatHeaderHeading } = await import("../components/chat/ChatInterface");
    const html = renderToStaticMarkup(<ChatHeaderHeading>Mi chat</ChatHeaderHeading>);
    assert.match(html, /^<h1 [^>]*>Mi chat<\/h1>$/);
  });
});

test("the action cluster keeps the right edge without a heading to push it", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(new URL("../components/chat/ChatInterface.tsx", import.meta.url), "utf8");
  assert.ok(source.includes("`ml-auto flex shrink-0 justify-end pointer-events-auto"));
});

describe("sidebar header toggle label", () => {
  const cases = [
    ["es-419", true, "Contraer"],
    ["es-419", false, "Expandir"],
    ["en", true, "Collapse"],
    ["en", false, "Expand"],
  ] as const;
  for (const [lng, isOpen, label] of cases) {
    test(`${lng} ${isOpen ? "open" : "closed"} reads ${label}`, async () => {
      const { default: SidebarHeader } = await import("../components/sidebar/SidebarHeader");
      const i18n = await i18nFor(lng);
      const html = renderToStaticMarkup(
        <I18nextProvider i18n={i18n}>
          <SidebarHeader variant="rail" isOpen={isOpen} onToggle={() => undefined} />
        </I18nextProvider>,
      );
      assert.ok(html.includes(`aria-label="${label}"`), html);
    });
  }
});

describe("Controles de datos in Ajustes", () => {
  async function mountOpenDataMenu(calls: string[]) {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const { default: ProfileMenu } = await import("../components/sidebar/ProfileMenu");
    const i18n = await i18nFor("es-419");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const anchor = document.createElement("button");
    document.body.appendChild(anchor);
    const root = createRoot(host);
    await act(async () => {
      root.render(
        <I18nextProvider i18n={i18n}>
          <ProfileMenu
            isOpen
            onClose={() => calls.push("close")}
            onLogout={() => undefined}
            anchorRef={{ current: anchor }}
          />
        </I18nextProvider>,
      );
    });
    const trigger = Array.from(document.body.querySelectorAll("button")).find((b) =>
      b.textContent?.trim() === "Ajustes",
    )!;
    await act(async () => {
      trigger.click();
    });
    unmounts.push(() => act(async () => root.unmount()));
    return { act, host };
  }

  test("Security, then delete account last, with no Usage or delete-all row", async () => {
    const calls: string[] = [];
    await mountOpenDataMenu(calls);
    const rows = Array.from(document.body.querySelectorAll("[data-settings-row]")).map((row) => row.textContent?.trim());
    const usage = rows.indexOf("Uso");
    const security = rows.indexOf("Seguridad");
    const deleteAccount = rows.indexOf("Eliminar cuenta");
    assert.equal(rows.indexOf("Eliminar todas las conversaciones"), -1);
    assert.equal(usage, -1, "Retired Usage has no settings row");
    assert.ok(security > -1, "Security remains available");
    assert.equal(deleteAccount, rows.length - 1, "nothing follows delete account");
    assert.deepEqual(calls, ["close"], "the menu closes under Ajustes");
  });

  test("Eliminar cuenta opens its confirm dialog and requests nothing", async () => {
    const calls: string[] = [];
    const originalFetch = globalThis.fetch;
    const fetched: string[] = [];
    globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
      fetched.push(`${init?.method ?? "GET"} ${String(input)}`);
      return new Response("{}");
    }) as typeof fetch;
    const { act } = await mountOpenDataMenu(calls);
    const account = Array.from(document.body.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Eliminar cuenta"),
    )!;
    const before = fetched.length;
    try {
      await act(async () => account.click());
      assert.ok(document.querySelector("[role=dialog],[aria-modal=true]"), "confirm dialog is open");
      assert.deepEqual(fetched.slice(before).filter((call) => !call.startsWith("GET ")), [], "opening the dialog only reads; it sends no deletion request");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
