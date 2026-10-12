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
  test("one row shows the server disclosure and models beside a switch that is off", () => {
    const html = render({ status: linked, consent });
    expect(html).toContain("Let AI read my WhatsApp messages");
    expect(html).toContain("Cuadrao sends your message text to an AI provider");
    expect(html).toContain("anthropic/claude-haiku-5.5");
    expect(html).toMatch(/role="switch"[^>]*aria-checked="false"/);
    expect(html).not.toMatch(/role="switch"[^>]*\sdisabled=""/);
    expect(html).toContain("You always approve money records yourself");
    expect(html).not.toContain('type="checkbox"');
  });

  test("an enabled permission shows the switch on, one tap from off", () => {
    const html = render({ status: linked, consent: { ...consent, enabled: true } });
    expect(html).toMatch(/role="switch"[^>]*aria-checked="true"/);
    expect(html).toContain("On. You can turn it off at any time.");
    expect(html).not.toMatch(/role="switch"[^>]*\sdisabled=""/);
  });

  test("an unavailable permission says why and the switch cannot be turned on", () => {
    const html = render({ status: linked, consent: { ...consent, available: false, reason: "business_unavailable", disclosure_token: null } });
    expect(html).toContain("Create your business space first.");
    expect(html).toMatch(/role="switch"[^>]*\sdisabled=""/);
  });

  test("an unlinked owner sees no AI row", () => {
    expect(render({ consent })).not.toContain("Let AI read my WhatsApp messages");
  });

  test("Spanish first copy renders", () => {
    const html = render({ status: linked, consent }, "es-419");
    expect(html).toContain("Permitir que la IA lea mis mensajes de WhatsApp");
    expect(html).toContain("Desactivado. Cuadrao todavía no puede responder tus mensajes.");
  });

  test("only a signed 64 character disclosure token can enable", async () => {
    const { canEnableAI } = await import("../lib/whatsapp-link-api");
    expect(canEnableAI(consent)).toBe(true);
    expect(canEnableAI({ ...consent, disclosure_token: "short" })).toBe(false);
    expect(canEnableAI({ ...consent, enabled: true })).toBe(false);
    expect(canEnableAI({ ...consent, route: null })).toBe(false);
  });
});


describe("WhatsApp AI permission, one tap", () => {
  const client = (overrides: Record<string, unknown> = {}) => {
    const calls: string[] = [];
    return {
      calls,
      client: {
        enable: async (token: string, key: string) => {
          calls.push(`enable:${token}:${key}`);
          return { ...consent, enabled: true };
        },
        revoke: async () => {
          calls.push("revoke");
        },
        read: async () => {
          calls.push("read");
          return { ...consent, enabled: false };
        },
        newKey: () => `key-${calls.length}`,
        ...overrides,
      },
    };
  };

  test("on sends the server's disclosure token and a fresh key, and returns the server's answer", async () => {
    const { toggleWhatsAppAI } = await import("../lib/whatsapp-link-api");
    const { calls, client: api } = client();
    const next = await toggleWhatsAppAI(consent, api);
    expect(calls).toEqual([`enable:${"a".repeat(64)}:key-0`]);
    expect(next.enabled).toBe(true);
  });

  test("off revokes once and reads the new state", async () => {
    const { toggleWhatsAppAI } = await import("../lib/whatsapp-link-api");
    const { calls, client: api } = client();
    const next = await toggleWhatsAppAI({ ...consent, enabled: true }, api);
    expect(calls).toEqual(["revoke", "read"]);
    expect(next.enabled).toBe(false);
  });

  test("a revoke that worked shows off even when the follow-up read fails", async () => {
    const { toggleWhatsAppAI } = await import("../lib/whatsapp-link-api");
    const { client: api } = client({ read: async () => { throw new Error("offline"); } });
    const next = await toggleWhatsAppAI({ ...consent, enabled: true }, api);
    expect(next.enabled).toBe(false);
  });

  test("a failed enable or revoke throws, so the screen keeps the old state", async () => {
    const { toggleWhatsAppAI } = await import("../lib/whatsapp-link-api");
    const fail = async () => { throw Object.assign(new Error("x"), { status: 500, code: "x" }); };
    await expect(toggleWhatsAppAI(consent, client({ enable: fail }).client)).rejects.toThrow();
    await expect(toggleWhatsAppAI({ ...consent, enabled: true }, client({ revoke: fail }).client)).rejects.toThrow();
  });

  test("a stale disclosure (409) is its own problem, not 'could not be reached'", async () => {
    expect(whatsAppLinkProblem({ status: 409, code: "whatsapp_ai_consent_disclosure_changed" })).toBe("stale");
    const html = render({ status: linked, consent, problem: "stale" });
    expect(html).toContain("The text changed since you last read it.");
  });

  test("a missing disclosure cannot be turned on and does not crash", async () => {
    const { canEnableAI } = await import("../lib/whatsapp-link-api");
    expect(canEnableAI({ ...consent, disclosure: null as unknown as string })).toBe(false);
    expect(() => render({ status: linked, consent: { ...consent, disclosure: null as unknown as string } })).not.toThrow();
  });
});
