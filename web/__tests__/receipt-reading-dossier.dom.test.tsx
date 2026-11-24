import assert from "node:assert/strict";
import { test } from "bun:test";
import { withReceiptReading } from "./support/receipt-reading";
import { mount, registerReceiptReviewPage } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

const row = (host: Element) => host.querySelector<HTMLElement>('[data-testid="receipt-reading-control"]');
const openSaved = async (enabled: boolean) => {
  const page = await mount(() => withReceiptReading({ enabled, disclosure: "Permiso de prueba" }));
  await page.open({ kind: "receipt", receiptId: "rcpt-saved" }, () => page.frame().fields !== null);
  return page;
};

test("the dossier of a document saved unread shows the reading row only while reading is off, and turns it on in place", async () => {
  const off = await openSaved(false);
  try {
    await off.wait(() => row(off.host) !== null);
    const toggle = row(off.host)!.querySelector<HTMLButtonElement>('[role="switch"]')!;
    assert.deepEqual([...row(off.host)!.querySelectorAll("button")], [toggle], "no button opens another panel");
    await off.act(async () => toggle.click());
    const consent = row(off.host)!.querySelector('[data-testid="receipt-reading-consent"]')!;
    assert.equal(consent.querySelector("p")?.textContent, "Permiso de prueba");
    await off.act(async () => { consent.querySelector("button")!.click(); await Promise.resolve(); });
    await off.wait(() => row(off.host) === null);
    assert.equal(off.host.textContent?.includes("Permiso de prueba"), false);
  } finally { await off.act(async () => off.root.unmount()); }

  const on = await openSaved(true);
  try {
    assert.equal(row(on.host), null);
    assert.equal(on.host.querySelector('[data-testid="receipt-reading-switch"]'), null);
  } finally { await on.act(async () => on.root.unmount()); }
});
