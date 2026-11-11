import { afterEach, describe, expect, test } from "bun:test";
import { isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { createInstance } from "i18next";
import ShareReceiptAction from "../components/chat/ShareReceiptAction";
import { ReceiptTurnChoice } from "../components/chat/ReceiptConversationSelection";
import ReceiptNotice from "../components/receipt/ReceiptNotice";
import ReceiptActionBar from "../components/receipt/ReceiptActionBar";
import { receiptCopy } from "../lib/receipt-copy";
import { normalizeEnabledLanguage } from "../lib/language-features";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

const noop = () => {};
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

describe.each(["en", "es-419"] as const)("share surfaces in %s", (languageValue) => {
  const language = languageValue as "en" | "es-419";
  test("the transcript choice names the question and answer, with private turns disabled", async () => {
    const i18n = createInstance();
    await i18n.init({ lng: language, resources: { en: { translation: en }, "es-419": { translation: es } } });
    const markup = renderToStaticMarkup(<I18nextProvider i18n={i18n}><ReceiptTurnChoice candidate={{ message_id: "private", eligible: false, reason: "unsafe_text", field: "answer" }} selected={false} onToggle={noop} /></I18nextProvider>);
    expect(markup).toContain('type="checkbox"');
    expect(markup).toContain('disabled=""');
    expect(markup).toContain(receiptCopy(normalizeEnabledLanguage(language)).selection.choose_turn);
    expect(markup).toContain(receiptCopy(normalizeEnabledLanguage(language)).selection.reasons.unsafe_text);
  });

  test("header shortcut announces sharing the conversation, not creating a link", async () => {
    const i18n = createInstance();
    await i18n.init({ lng: language, resources: { en: { translation: en }, "es-419": { translation: es } } });
    const markup = renderToStaticMarkup(<I18nextProvider i18n={i18n}><ShareReceiptAction conversationId="conversation" onShare={noop} /></I18nextProvider>);
    expect(markup).toContain(`aria-label="${receiptCopy(language).selection.title}"`);
    expect(markup).not.toContain(receiptCopy(language).owner.create);
    expect(markup).not.toContain("conversationId");
  });
});

test.each(["revoked", "unavailable"] as const)("%s links keep the bare CTA", (kind) => {
  const view = ReceiptNotice({ kind, copy: receiptCopy("en") });
  const markup = renderToStaticMarkup(view);
  expect(markup.match(/href="([^"]+)"/)?.[1]).toBe("/");
  expect(markup).toContain(receiptCopy("en").cta.action);
});

test("an unknown link CTA does not invent a backtest funnel event", () => {
  const requests: unknown[] = [];
  globalThis.fetch = (async (_url, init) => { requests.push(init?.body); return Response.json({}); }) as typeof fetch;
  function clickLink(node: ReactNode): void {
    if (Array.isArray(node)) { node.forEach(clickLink); return; }
    if (!isValidElement<{ children?: ReactNode; href?: string; onClick?: () => void }>(node)) return;
    if (node.props.href === "/") node.props.onClick?.();
    clickLink(node.props.children);
  }
  clickLink(ReceiptActionBar({ framing: "Context", action: "Continue with Argus" }));
  expect(requests).toEqual([]);
});
