import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

for (const kind of ["more", "popover"] as const) {
  test(`${kind}: first Escape closes only the open control; second closes the record panel`, async () => {
    const { act, useRef, useState } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const { I18nextProvider } = await import("react-i18next");
    const i18next = (await import("i18next")).default;
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const AdaptivePanel = (await import("@/components/ui/AdaptivePanel")).default;
    const { ReceiptMoreMenu } = await import("@/components/business-app/ReceiptReviewFooter");
    const { usePopover } = await import("@/components/business-app/dossier/DossierParts");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    let closes = 0;
    function Popover() {
      const host = useRef<HTMLDivElement>(null);
      const [open, setOpen] = useState(false);
      usePopover(host, open, () => setOpen(false));
      return <div ref={host}><button aria-expanded={open} onClick={() => setOpen(true)}>Open</button>{open ? <button role="option">Option</button> : null}</div>;
    }
    function View() {
      const [open, setOpen] = useState(true);
      return <I18nextProvider i18n={i18n}>{open ? <AdaptivePanel title="Synthetic record" modal={false} onClose={() => { closes += 1; setOpen(false); }}>
        {kind === "more" ? <ReceiptMoreMenu groups={[<button key="action" role="menuitem">Action</button>]} /> : <Popover />}
        <button data-after-menu="">Next field</button>
      </AdaptivePanel> : null}</I18nextProvider>;
    }
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    try {
      await act(async () => root.render(<View />));
      const trigger = document.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
      assert.ok(trigger);
      await act(async () => trigger.click());
      assert.equal(trigger.getAttribute("aria-expanded"), "true");
      // Tab can leave this non-modal menu while it remains open.
      document.querySelector<HTMLButtonElement>("[data-after-menu]")!.focus();
      const escape = () => act(async () => {
        (document.activeElement ?? trigger).dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
      });
      await escape();
      assert.equal(closes, 0, "the panel stays open after the first Escape");
      assert.equal(trigger.getAttribute("aria-expanded"), "false");
      await escape();
      assert.equal(closes, 1);
    } finally {
      await act(async () => root.unmount());
      host.remove();
    }
  });
}
