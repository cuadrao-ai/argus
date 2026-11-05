import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import ChatMessage from "../components/chat/ChatMessage";
import type { Message } from "../components/chat/types";
import { translate } from "./support/i18n-instance";

import SafeMarkdown from "../components/chat/SafeMarkdown";
import ReceiptTurnContent from "../components/receipt/ReceiptTurnContent";
import ToolCardPresentation from "../components/chat/ToolCardPresentation";
import { receiptCopy } from "../lib/receipt-copy";
import { receiptPresentations } from "../lib/receipt-presentation";
import { researchTurn } from "./fixtures/receipt-turns";
import calculationFixture from "./fixtures/calculation-cards.json";
import type { ToolResultCard } from "../lib/tool-result-card";
import nextConfig from "../next.config";


const markdown = 'Readable **answer** ![Chart description](https://tracking.invalid/pixel.png) and [source](https://example.org/report).';

describe("chat Markdown image privacy", () => {
  test.each([false, true])("renders image descriptions without fetchable images, shared=%s", async (shared) => {
    const i18n = await translate("en");
    const message: Message = { id: "image-policy", role: "ai", content: markdown,
      ...(shared ? { sharedConversation: { snapshot_at: "2026-09-26T12:00:00Z" } } : {}),
    };
    const html = renderToStaticMarkup(<I18nextProvider i18n={i18n}><ChatMessage message={message} /></I18nextProvider>);
    expect(html).not.toContain("<img");
    expect(html).not.toContain("tracking.invalid");
    expect(html).toContain("Chart description");
    expect(html).toContain('href="https://example.org/report"');
  });
});


test.each([
  '![Chart description](//tracking.invalid/pixel)',
  '![Chart description][image]\n\n[image]: https://tracking.invalid/pixel',
  '![Chart description](/api/pixel)',
  '![Chart description](data:image/png;base64,aGVsbG8=)',
  '<img src="https://tracking.invalid/pixel" />',
])("never emits an image or image preload for %s", (content) => {
  const html = renderToStaticMarkup(<SafeMarkdown>{String(content)}</SafeMarkdown>);
  expect(html).not.toContain("<img");
  expect(html).not.toContain("preload");
  expect(html).not.toContain("tracking.invalid");
});

test("public research receipts retain image descriptions and ordinary source links", () => {
  const turn = { ...researchTurn, answer: markdown };
  const entry = receiptPresentations({ schema_version: 2, kind: "turns", turns: [turn] }, "2026-09-26T12:00:00Z", "en")[0];
  const html = renderToStaticMarkup(<ReceiptTurnContent entry={entry} copy={receiptCopy("en")} language="en" />);
  expect(html).not.toContain("<img");
  expect(html).not.toContain("tracking.invalid");
  expect(html).toContain("Chart description");
  expect(html).toContain('href="https://example.org/report"');
});

test("tool card narratives share the image policy", () => {
  const card = calculationFixture.cards.growth_projection.card as ToolResultCard;
  const html = renderToStaticMarkup(<ToolCardPresentation presentation={{ ...card.presentation, narrative: markdown }} t={(key) => key} locale="en" />);
  expect(html).not.toContain("<img");
  expect(html).not.toContain("tracking.invalid");
  expect(html).toContain("Chart description");
});

test("Markdown retains unsafe URL sanitization", () => {
  const html = renderToStaticMarkup(<SafeMarkdown>{"[unsafe](javascript:alert%281%29)"}</SafeMarkdown>);
  expect(html).not.toContain("javascript:");
  expect(html).toContain("unsafe");
});

test("image CSP allows local assets and embedded images without remote origins", async () => {
  const headers = await nextConfig.headers!();
  expect(headers).toContainEqual({ source: "/:path*", headers: [{ key: "Content-Security-Policy", value: "img-src 'self' data:;" }] });
});
