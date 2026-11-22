import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import ReceiptChart from "../components/receipt/ReceiptChart";

test("tool-card charts retain visible attribution", () => {
  const markup = renderToStaticMarkup(<ReceiptChart visual={{ kind: "value_path", series: [
    { time: "2026-01-01", value: 100 },
    { time: "2026-02-01", value: 118 },
  ] }} />);
  expect(markup).toContain('data-testid="receipt-chart-attribution"');
  expect(markup).toContain('target="_blank"');
});

test("receipt charts retain the library attribution logo", () => {
  const source = readFileSync(new URL("../components/receipt/ReceiptChart.tsx", import.meta.url), "utf8");
  expect(source).toContain("attributionLogo: true");
  expect(source).not.toContain("attributionLogo: false");
});
