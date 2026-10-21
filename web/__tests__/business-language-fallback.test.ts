import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "bun:test";

const root = join(import.meta.dir, "..");
const businessApp = join(root, "components/business-app");

/** A shown language picked from a literal instead of resolveLanguage, or a branch on the language outside the catalog. */
const LITERAL_LANGUAGE = /(?:resolvedLanguage|i18n\.language)(?:\s*\?\?\s*i18n\.language)?\s*(?:\?\?|===|!==)\s*["'][\w-]+["']|(?:resolvedLanguage|i18n\.language)\)?\.startsWith\(/g;

/** Sites that still carry a literal fallback, each to move onto resolveLanguage and leave this list. */
const NOT_YET_MOVED: Record<string, number> = {
  "components/business-app/BusinessAccessPanel.tsx": 1,
  "components/business-app/BusinessEmailDeliveries.tsx": 3,
  "components/business-app/BusinessInboxPanel.tsx": 3,
  "components/business-app/BusinessMonthClosePanel.tsx": 1,
  "components/business-app/BusinessPeriodControl.tsx": 1,
  "components/business-app/BusinessSearchDossier.tsx": 3,
  "components/business-app/ExpenseDetailPanel.tsx": 1,
  "components/business-app/OutsidePeriodNote.tsx": 1,
  "components/business-app/ReceiptEcfChecks.tsx": 1,
  "components/business-app/ReceiptHistory.tsx": 1,
  "components/business-app/ReceiptMessages.tsx": 3,
  "components/business-app/ReceiptReadingControl.tsx": 1,
  "components/business-app/ReceiptRecordFacts.tsx": 1,
  "components/business-app/ReceiptReviewPanel.tsx": 1,
  "components/business-app/ReceiptSourcePreview.tsx": 1,
  "components/business-app/useBusinessSearch.ts": 1,
};

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

test("Business picks the shown language through resolveLanguage, never a literal or a Spanish branch", () => {
  const found = Object.fromEntries(
    sources(businessApp)
      .map((path) => [relative(root, path), readFileSync(path, "utf-8").match(LITERAL_LANGUAGE)?.length ?? 0] as const)
      .filter(([, count]) => count > 0),
  );
  assert.deepEqual(found, NOT_YET_MOVED);
});
