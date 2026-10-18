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

describe("Controles de datos danger group", () => {
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
            onDeleteAllConversations={() => calls.push("delete-all")}
            anchorRef={{ current: anchor }}
          />
        </I18nextProvider>,
      );
    });
    const trigger = Array.from(document.body.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Controles de datos"),
    )!;
    await act(async () => {
      trigger.click();
    });
    unmounts.push(() => act(async () => root.unmount()));
    return { act, host };
  }

  test("Usage, a separator, then both danger rows in that order, with confirm steps intact", async () => {
    const calls: string[] = [];
    const { act } = await mountOpenDataMenu(calls);
    const usageButton = Array.from(document.body.querySelectorAll("button")).find(
      (b) => b.textContent?.trim().startsWith("Uso"),
    )!;
    const rows = Array.from(usageButton.parentElement!.querySelectorAll(":scope > button, :scope > [role=separator]"));
    const index = (text: string) =>
      rows.findIndex((n) => n.textContent?.trim().startsWith(text));
    const usage = index("Uso");
    const deleteAll = index("Eliminar todas las conversaciones");
    const deleteAccount = index("Eliminar cuenta");
    const separator = rows.findIndex((n) => n.getAttribute("role") === "separator" && rows.indexOf(n) > usage);
    assert.ok(usage > -1 && deleteAll > -1 && deleteAccount > -1, "rows present");
    assert.ok(separator > usage, "a separator follows Usage");
    assert.ok(separator < deleteAll, "the separator sits above the first danger row");
    assert.ok(deleteAll < deleteAccount, "delete account is last");
    assert.equal(rows.length - 1, deleteAccount, "nothing follows the danger group");

    await act(async () => (rows[deleteAll] as HTMLButtonElement).click());
    assert.deepEqual(calls, ["close", "delete-all"], "delete all hands off to its confirm dialog, deleting nothing itself");
  });

  test("Eliminar cuenta opens its confirm dialog and requests nothing", async () => {
    const calls: string[] = [];
    const originalFetch = globalThis.fetch;
    const fetched: string[] = [];
    globalThis.fetch = (async (input: unknown) => {
      fetched.push(String(input));
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
      assert.equal(fetched.length, before, "opening the dialog sends no deletion request");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
