import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { BusinessActor, BusinessDossier, BusinessDraftRevision, BusinessFacts } from "@/lib/business-dossier";
import type { PersonShown } from "@/lib/person-name";

mock.module("next/navigation", () => ({
  usePathname: () => "/biz",
  useRouter: () => ({ push: () => {}, replace: () => {}, refresh: () => {}, prefetch: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function render(node: ReactNode, language: "es-419" | "en") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const translation = (await import(`@/public/locales/${language}/common.json`)).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { [language]: { translation } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>); });
  return { host, act, close: () => act(async () => { root.unmount(); host.remove(); }) };
}

const known = <T,>(value: T) => ({ state: "known" as const, value, origin: "member_set" as const, verified: false, source_ids: [] });
const unknown = { state: "unknown" as const, value: null, origin: null, verified: false as const, source_ids: [] };
const facts = (amount: string) => ({ kind: known("expense"), amount: known(amount), currency: known("DOP"), occurred_on: known("2026-10-09"), counterparty: known("Ferretería La Esquina"), funding: unknown, business_share: unknown, receipt_state: unknown, category_id: unknown, fiscal: null }) as unknown as BusinessFacts;
const actor = (id: string, display_name: string | null, email: string | null, shown_as: PersonShown): BusinessActor => ({ actor_id: id, actor_kind: "member", display_name, email, shown_as, grant_id: "g", issuer_id: "o", issuer_display_name: null, issuer_email: "dueno@example.test", issuer_shown_as: "email" });
const revision = (version: number, at: string, who: BusinessActor, amount: string): BusinessDraftRevision => ({ draft_id: "d", version, actor: who, before: facts("1.00"), after: facts(amount), source_ids: [], turn_key: null, created_at: at });

describe("people on the screen", () => {
  for (const language of ["es-419", "en"] as const) {
    test(`a person reads as the server shows them: name, email, member or former member (${language})`, async () => {
      const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
      const history = [
        revision(1, "2026-10-10T13:00:00Z", actor("a", null, "contadora@example.test", "email"), "10.00"),
        revision(2, "2026-10-10T14:00:00Z", actor("b", null, null, "former"), "20.00"),
        revision(3, "2026-10-10T15:00:00Z", actor("c", null, null, "member"), "30.00"),
        revision(4, "2026-10-10T16:00:00Z", actor("d", "Ana Peña", null, "name"), "40.00"),
      ];
      const approval = { status: "recorded", activity_id: "x", reviewed_version: 4, approved_revision: 4, approved_at: "2026-10-10T17:00:00Z", actor: actor("o", null, "dueno@example.test", "email") } as BusinessDossier["approval_result"];
      const page = await render(<ReceiptHistory history={history} accounts={[]} approval={approval} />, language);
      const section = page.host.querySelector('[data-testid="receipt-history"]')!;
      const text = section.textContent ?? "";
      const [former, member] = language === "en" ? ["Former member", "Member"] : ["Exmiembro", "Miembro"];
      for (const shown of ["contadora@example.test", "dueno@example.test", "Ana Peña", former, member]) assert.ok(text.includes(shown), shown);
      assert.equal(text.split(former).length - 1, 1, "the one who left");
      const who = [...section.querySelectorAll('[data-testid="history-who"] span')].map((name) => name.textContent);
      assert.equal(who.filter((name) => name === member).length, 1, "the unnamed teammate this viewer may not read the email of");
      assert.doesNotMatch(text, /null/);
      await page.close();
    });
  }

  test("each way a person shows reads its own words, and nothing else", async () => {
    const { personName } = await import("@/lib/person-name");
    const words: Record<string, string> = { "business.activity_feed.former_member": "Exmiembro", "business_access.member": "Miembro" };
    const t = ((key: string) => words[key] ?? key) as never;
    assert.equal(personName(t, { display_name: "Ana", email: null, shown_as: "name" }), "Ana");
    assert.equal(personName(t, { display_name: null, email: "a@example.test", shown_as: "email" }), "a@example.test");
    assert.equal(personName(t, { display_name: null, email: null, shown_as: "member" }), "Miembro");
    assert.equal(personName(t, { display_name: null, email: null, shown_as: "former" }), "Exmiembro");
    assert.equal(personName(t, null), "Exmiembro");
  });
});
