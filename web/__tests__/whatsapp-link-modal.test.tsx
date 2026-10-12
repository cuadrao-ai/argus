import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { WhatsAppLinkView, type WhatsAppLinkViewProps } from "../components/settings/WhatsAppLinkModal";
import { whatsAppLinkProblem } from "../lib/whatsapp-link-api";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

const noop = () => {};
const base: WhatsAppLinkViewProps = {
  status: { linked: false, last4: null, linked_at: null, reply_language: null },
  code: null,
  loading: false,
  busy: false,
  problem: null,
  confirmingUnlink: false,
  onCreateCode: noop,
  onAskUnlink: noop,
  onUnlink: noop,
  onRefresh: noop,
};

function render(props: Partial<WhatsAppLinkViewProps>, lng: "en" | "es-419" = "en") {
  const i18n = i18next.createInstance();
  void i18n.init({ lng, resources: { en: { translation: en }, "es-419": { translation: es } }, interpolation: { escapeValue: false } });
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <WhatsAppLinkView {...base} {...props} />
    </I18nextProvider>,
  );
}

describe("WhatsApp link view", () => {
  test("an unlinked owner can ask for a code", () => {
    const html = render({});
    expect(html).toContain("No number is linked.");
    expect(html).toContain("Get a link code");
    expect(html).not.toContain("Unlink number");
  });

  test("a code shows the message and the wa.me link", () => {
    const html = render({ code: { code: "ABCD2345", message_text: "CUADRAO ABCD2345", expires_at: "2026-10-12T10:00:00Z", wa_me_url: "https://wa.me/15551230000?text=CUADRAO%20ABCD2345" } });
    expect(html).toContain("CUADRAO ABCD2345");
    expect(html).toContain('href="https://wa.me/15551230000?text=CUADRAO%20ABCD2345"');
    expect(html).toContain("Get a new code");
  });

  test("without a display number the message is still shown", () => {
    const html = render({ code: { code: "ABCD2345", message_text: "CUADRAO ABCD2345", expires_at: "2026-10-12T10:00:00Z", wa_me_url: null } });
    expect(html).toContain("CUADRAO ABCD2345");
    expect(html).not.toContain("Open WhatsApp</a>");
  });

  test("a linked owner sees the last four digits and can unlink", () => {
    const html = render({ status: { linked: true, last4: "4821", linked_at: "2026-10-12T10:00:00Z", reply_language: "es-419" } });
    expect(html).toContain("Number ending in 4821");
    expect(html).toContain("Unlink number");
    expect(html).not.toContain("Get a link code");
  });

  test("unlinking asks first", () => {
    const html = render({ status: { linked: true, last4: "4821", linked_at: null, reply_language: null }, confirmingUnlink: true });
    expect(html).toContain("Receipts already received stay in your Inbox.");
  });

  test("a missing Business space blocks the code and says why", () => {
    const html = render({ problem: "space_missing" });
    expect(html).toContain("Start your business space first");
    expect(html).toMatch(/<button[^>]*\sdisabled=""[^>]*>Get a link code/);
  });

  test("Spanish copy renders", () => {
    expect(render({}, "es-419")).toContain("Obtener un código");
  });

  test("problems map from the API answer", () => {
    expect(whatsAppLinkProblem({ status: 404, code: "business_space_missing" })).toBe("space_missing");
    expect(whatsAppLinkProblem({ status: 404, code: "whatsapp_unavailable" })).toBe("unavailable");
    expect(whatsAppLinkProblem({ status: 429, code: "whatsapp_link_code_rate_limited" })).toBe("rate_limited");
    expect(whatsAppLinkProblem(new Error("network"))).toBe("failed");
  });
});

const linked = { linked: true, last4: "4821", linked_at: "2026-10-12T10:00:00Z", reply_language: "es-419" as const };
const consent = {
  linked: true,
  available: true,
  reason: null,
  last4: "4821",
  scope_version: 1,
  purpose: "business_whatsapp_draft_assistance",
  disclosure: "Cuadrao sends your message text to an AI provider to prepare drafts.",
  route: {
    gateway: "openrouter",
    interpretation: [{ model: "anthropic/claude-haiku-5.5" }],
    reply: [{ model: "anthropic/claude-haiku-5.5" }],
  },
  disclosure_token: "a".repeat(64),
  enabled: false,
  consented_at: null,
  revoked_at: null,
};

describe("WhatsApp AI permission", () => {
  test("an owner reads the disclosure and models before agreeing, and cannot enable without the box", () => {
    const html = render({ status: linked, consent });
    expect(html).toContain("Cuadrao sends your message text to an AI provider");
    expect(html).toContain("anthropic/claude-haiku-5.5");
    expect(html).toContain("Turn on AI reading");
    expect(html).toMatch(/<button[^>]*\sdisabled=""[^>]*>Turn on AI reading/);
    expect(html).toContain("You always approve money records yourself");
  });

  test("with the box checked the button is live", () => {
    expect(render({ status: linked, consent, agreed: true })).not.toMatch(/<button[^>]*\sdisabled=""[^>]*>Turn on AI reading/);
  });

  test("an enabled permission can be turned off and shows no disclosure form", () => {
    const html = render({ status: linked, consent: { ...consent, enabled: true } });
    expect(html).toContain("AI reading is on for this number.");
    expect(html).toContain("Turn off AI reading");
    expect(html).not.toContain("Turn on AI reading");
  });

  test("an unavailable permission says why in plain words and offers no switch", () => {
    const html = render({ status: linked, consent: { ...consent, available: false, reason: "business_unavailable", disclosure_token: null } });
    expect(html).toContain("Create your business space first.");
    expect(html).not.toContain("Turn on AI reading");
  });

  test("an unlinked owner sees no AI section", () => {
    expect(render({ consent })).not.toContain("AI reading of your messages");
  });

  test("Spanish first copy renders", () => {
    expect(render({ status: linked, consent }, "es-419")).toContain("Activar lectura con IA");
  });

  test("only a signed 64 character disclosure token can enable", async () => {
    const { canEnableAI } = await import("../lib/whatsapp-link-api");
    expect(canEnableAI(consent)).toBe(true);
    expect(canEnableAI({ ...consent, disclosure_token: "short" })).toBe(false);
    expect(canEnableAI({ ...consent, enabled: true })).toBe(false);
    expect(canEnableAI({ ...consent, route: null })).toBe(false);
  });
});
