import assert from "node:assert/strict";
import { test } from "bun:test";
import type { ReceiptDetail } from "@/lib/business-api";
import { mount, registerReceiptReviewPage } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

type Activity = NonNullable<ReceiptDetail["activity"]>["state"];

// Every receipt state with no draft whose only document action is its deletion.
const DELETE_ONLY: [name: string, id: string, activity: Activity | null][] = [
  ["saved unread", "rcpt-saved", "saved_unread"],
  ["waiting for its read", "rcpt-saved", "reading"],
  ["with several purchases", "rcpt-ambiguous", null],
];

for (const [name, id, activity] of DELETE_ONLY) {
  test(`a receipt ${name} names Eliminar documento at the footer's left instead of a Más menu of one`, async () => {
    const page = await mount((fixture) => ({
      receipt: async (asked: string, signal?: AbortSignal): Promise<ReceiptDetail> => {
        const found = await fixture.receipt(asked, signal);
        return { ...found, email_original: false, delete_available: true, ...(activity ? { activity: { state: activity, unread: true, completion_cursor: null } } : {}) };
      },
      deleteDocument: async () => { throw new Error("the test confirms no deletion"); },
    }));
    const footer = () => page.host.querySelector<HTMLElement>('[data-testid="receipt-review-footer"]');
    await page.open({ kind: "receipt", receiptId: id }, () => footer() !== null);
    assert.equal(footer()!.querySelector('[data-testid="receipt-more"]'), null, "no Más menu");
    const [first] = footer()!.querySelectorAll("button");
    assert.equal(first.getAttribute("aria-label"), "Eliminar documento");
    assert.equal(first.getAttribute("aria-haspopup"), null, "the action itself, not a menu");
    await page.act(async () => first.click());
    await page.wait(() => document.querySelector('[role="dialog"], [role="alertdialog"]') !== null);
    await page.act(async () => page.root.unmount());
  });
}
