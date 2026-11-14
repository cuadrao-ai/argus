import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace } from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";

let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));
mock.module("@/lib/business-activity-api", () => ({
  getBusinessActivity: async () => ({ items: [], next_cursor: null }),
}));

const dismissed = new Set<string>();
const guideRequests: string[] = [];
let registeredFetch: typeof globalThis.fetch;
const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  registeredFetch = globalThis.fetch;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async (input, init) => {
    const guide = /\/business\/guide-cards\/([^/]+?)(\/dismiss)?$/.exec(String(input));
    if (!guide) throw new Error("Unavailable");
    guideRequests.push(`${init?.method ?? "GET"} ${guide[0]}`);
    if (guide[2]) dismissed.add(guide[1]);
    return Response.json({ dismissed: dismissed.has(guide[1]) });
  };
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
  dismissed.clear();
  guideRequests.length = 0;
});
afterAll(async () => {
  globalThis.fetch = registeredFetch;
  if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock;
  await GlobalRegistrator.unregister();
});

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", business_role: "owner", permissions: ["read", "prepare", "approve", "manage", "assign_owner", "download", "export"], capabilities: ["read", "prepare", "approve"] } as GrantedSpace;
const LANGUAGES = { "es-419": spanish, en: english } as const;

async function mount(query: string, language: keyof typeof LANGUAGES = "es-419") {
  search = query;
  window.history.replaceState(null, "", `/biz?${query}`);
  const { act, useEffect } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { [language]: { translation: LANGUAGES[language] } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: true }), mode: "live", spaces: async () => [OWN], spaceDirectory: async () => ({ spaces: [OWN], closed_spaces: [] }) };
  const shell = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  function Shell() {
    const workspace = useChatWorkspace();
    const connect = workspace?.onShellChange;
    useEffect(() => { connect?.(shell as never); }, [connect]);
    return <main>{workspace?.panel(shell as never)}</main>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never} userId="ana">
            <Shell />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 120 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(done(), host.textContent ?? "");
  };
  const guide = () => host.querySelector<HTMLElement>("section[aria-labelledby]");
  const dismiss = () => {
    const button = [...host.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.getAttribute("aria-label") === LANGUAGES[language].business.guide_cards.placeholder.dismiss);
    assert.ok(button, "the guide's dismiss control");
    return act(async () => button.click());
  };
  return { host, settle, guide, dismiss, close: () => act(async () => root.unmount()) };
}

const LOCKED = {
  "es-419": {
    title: "Lo que pasa en tu negocio, en un solo lugar",
    points: [
      ["Sigue la actividad", "Ve quién subió, aprobó, editó o eliminó documentos, y cuándo."],
      ["Ve directo al documento", "Abre una fila para ir a ese documento o registro."],
      ["Nada se pierde de vista", "Lo que se borra definitivamente también queda anotado, aunque ya no se pueda abrir."],
    ],
  },
  en: {
    title: "What happens in your business, in one place",
    points: [
      ["Follow the activity", "See who uploaded, approved, edited or deleted documents, and when."],
      ["Go straight to it", "Open a row to go to that document or record."],
      ["Nothing slips by", "Permanently deleted documents are still noted here, even though they can't be opened."],
    ],
  },
} as const;

for (const language of ["es-419", "en"] as const) test(`Actividad shows its three-point guide in ${language} until the person dismisses it`, async () => {
  const page = await mount("view=activity", language);
  try {
    await page.settle(() => page.guide() !== null);
    const guide = page.guide()!;
    assert.ok(page.host.querySelector('[data-testid="business-activity-draft"]')?.contains(guide));
    assert.equal(guide.querySelector("h3")?.textContent, LOCKED[language].title);
    assert.deepEqual(
      [...guide.querySelectorAll("li")].map((item) => [item.querySelector("strong")?.textContent, item.querySelector("p")?.textContent]),
      LOCKED[language].points,
    );
    await page.dismiss();
    await page.settle(() => page.guide() === null);
    assert.deepEqual(guideRequests, ["GET /business/guide-cards/actividad-intro", "POST /business/guide-cards/actividad-intro/dismiss"]);
  } finally { await page.close(); }
  const again = await mount("view=activity", language);
  try {
    await again.settle(() => guideRequests.length === 3);
    assert.equal(again.guide(), null, "a dismissed guide stays hidden for the person");
  } finally { await again.close(); }
});

test("Bandeja keeps its three labeled points", async () => {
  const copy = spanish.business.guide_cards.bandeja_intro;
  const page = await mount("view=inbox");
  try {
    await page.settle(() => page.guide() !== null);
    assert.equal(page.guide()!.querySelector("h3")?.textContent, copy.title);
    assert.deepEqual(
      [...page.guide()!.querySelectorAll("li")].map((item) => [item.querySelector("strong")?.textContent, item.querySelector("p")?.textContent]),
      [[copy.upload.label, copy.upload.body], [copy.review.label, copy.review.body], [copy.pending.label, copy.pending.body]],
    );
    assert.deepEqual(guideRequests, ["GET /business/guide-cards/bandeja-intro"]);
  } finally { await page.close(); }
});
