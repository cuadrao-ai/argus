import assert from "node:assert/strict";
import { test } from "bun:test";
import { withReceiptReading } from "./support/receipt-reading";
import { mount, registerReceiptReviewPage } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

const row = (host: Element) => host.querySelector<HTMLElement>('[data-testid="receipt-reading-notice"]');
const openSaved = async (enabled: boolean) => {
  const page = await mount(() => withReceiptReading({ enabled, disclosure: "Permiso de prueba" }));
  await page.open({ kind: "receipt", receiptId: "rcpt-saved" }, () => page.frame().fields !== null);
  return page;
};

test("the dossier of a document saved unread shows the reading notice and its button only while reading is off, never a switch, and turns it on in place", async () => {
  const off = await openSaved(false);
  try {
    await off.wait(() => row(off.host) !== null);
    assert.match(row(off.host)!.textContent ?? "", /^La lectura automática está apagada\.Tú siempre revisas y aceptas\.Activar lectura de documentos$/);
    assert.equal(off.host.querySelector('[role="switch"]'), null, "no switch");
    const turnOn = row(off.host)!.querySelector<HTMLButtonElement>('[data-testid="receipt-reading-turn-on"]')!;
    assert.deepEqual([...row(off.host)!.querySelectorAll("button")], [turnOn], "the button is the notice's only control");
    await off.act(async () => turnOn.click());
    const consent = row(off.host)!.querySelector('[data-testid="receipt-reading-consent"]')!;
    assert.equal(consent.querySelector("p")?.textContent, "Permiso de prueba");
    await off.act(async () => { consent.querySelector("button")!.click(); await Promise.resolve(); });
    await off.wait(() => row(off.host) === null);
    assert.equal(off.host.textContent?.includes("Permiso de prueba"), false);
  } finally { await off.act(async () => off.root.unmount()); }

  const on = await openSaved(true);
  try {
    assert.equal(row(on.host), null);
    assert.equal(on.host.querySelector('[role="switch"]'), null);
    assert.equal(on.host.querySelector('[data-testid="receipt-reading-turn-on"]'), null);
  } finally { await on.act(async () => on.root.unmount()); }
});
