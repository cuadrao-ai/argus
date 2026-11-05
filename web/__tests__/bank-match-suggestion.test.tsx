import { beforeAll, describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";

import { BankMatchSuggestionCard, type BankMatchSuggestionCardProps } from "../components/business-app/BankMatchSuggestion";

const SIDEBAR_ICONS = [
  "lucide-bell",
  "lucide-inbox",
  "lucide-layout-grid",
  "lucide-receipt-text",
  "lucide-chevron-down",
  "lucide-history",
  "lucide-message-circle-plus",
  "lucide-pin",
  "lucide-search",
  "lucide-user",
];

const line = {
  occurredOn: "01/10/2026",
  description: "Ferretería Luna",
  amount: "-1500.00",
  currency: "DOP",
};

function props(kind: "receipt" | "venta"): BankMatchSuggestionCardProps {
  return {
    line,
    document: {
      kind,
      occurredOn: "01/10/2026",
      description: "Ferretería Luna",
      amount: "1500.00",
      currency: "DOP",
    },
    onConfirm: () => undefined,
    onDecline: () => undefined,
    enabled: true,
  };
}

beforeAll(async () => {
  await i18next.init({
    lng: "es-419",
    resources: {
      "es-419": {
        translation: {
          business: {
            bank: {
              suggestion: {
                confirm: "Confirmar",
                decline: "No es este",
                receipt: "Gasto",
                venta: "Venta",
              },
            },
          },
        },
      },
    },
    interpolation: { escapeValue: false },
  });
});

function html(node: ReturnType<typeof BankMatchSuggestionCard>) {
  return renderToStaticMarkup(createElement(I18nextProvider, { i18n: i18next }, node));
}

describe("bank match suggestion card", () => {
  test("puts the bank line and the document in one row", () => {
    const markup = html(<BankMatchSuggestionCard {...props("receipt")} />);
    expect(markup).toContain('data-testid="bank-match-row"');
    expect(markup).toContain("flex-row");
    expect(markup).toContain("flex-nowrap");
    expect(markup).not.toContain("flex-col");
    const row = markup.slice(markup.indexOf('data-testid="bank-match-row"'));
    const lineAt = row.indexOf('data-testid="bank-match-line"');
    const documentAt = row.indexOf('data-testid="bank-match-document"');
    expect(lineAt).toBeGreaterThan(0);
    expect(documentAt).toBeGreaterThan(lineAt);
  });

  test("gives Confirmar and No es este a 44px tap target", () => {
    const markup = html(<BankMatchSuggestionCard {...props("receipt")} />);
    expect(markup).toContain("Confirmar");
    expect(markup).toContain("No es este");
    const buttons = markup.match(/<button[\s\S]*?<\/button>/g) ?? [];
    expect(buttons).toHaveLength(2);
    for (const button of buttons) {
      expect(button).toContain("min-h-11");
      expect(button).toContain("min-w-11");
      expect(button).toContain("min-height:44px");
      expect(button).toContain("min-width:44px");
    }
  });

  test("shows Gasto or Venta as a label plus an icon outside the sidebar set", () => {
    const gasto = html(<BankMatchSuggestionCard {...props("receipt")} />);
    const venta = html(<BankMatchSuggestionCard {...props("venta")} />);
    expect(gasto).toContain("lucide-hand-coins");
    expect(gasto).toContain("Gasto");
    expect(venta).toContain("lucide-store");
    expect(venta).toContain("Venta");
    for (const markup of [gasto, venta]) {
      expect(markup).not.toContain("lucide-sparkles");
      for (const icon of SIDEBAR_ICONS) expect(markup).not.toContain(icon);
      const start = markup.indexOf('data-testid="bank-match-kind"');
      const kind = markup.slice(start, markup.indexOf("</p>", start));
      expect(kind).toContain("<svg");
      expect(kind).toMatch(/Gasto|Venta/);
    }
  });

  test("stays absent while the switch is off", () => {
    const markup = html(<BankMatchSuggestionCard {...props("receipt")} enabled={false} />);
    expect(markup).toBe("");
  });
});
