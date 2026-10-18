import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { useState } from "react";
import { BUSINESS_STATUS, CANVAS, CONFIRM_ACTION, LOADING_TRACK, PLAIN_TOAST_MS, UNDO_TOAST_MS, contrastRatio } from "@/components/business-app/foundation/presentation";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function render(node: import("react").ReactNode) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>);
  });
  return {
    host,
    act,
    close: () => act(async () => { root.unmount(); host.remove(); }),
  };
}

describe("status is a word, a color, and a dot", () => {
  test("each receipt status shows its Spanish name, ink, and dot", async () => {
    const { StatusPill } = await import("@/components/business-app/foundation/StatusPill");
    const page = await render(
      <>
        <StatusPill status="confirmed" />
        <StatusPill status="needs_attention" />
        <StatusPill status="saved" />
      </>,
    );
    const pills = [...page.host.querySelectorAll('[data-testid="status-pill"]')];
    assert.deepEqual(pills.map((pill) => pill.textContent), ["Aprobado", "Necesita atención", "Pendiente"]);
    assert.deepEqual(pills.map((pill) => pill.getAttribute("data-status")), ["approved", "needs_attention", "pending"]);
    const approved = BUSINESS_STATUS.approved;
    assert.match(pills[0].getAttribute("style") ?? "", new RegExp(approved.ink, "i"));
    assert.match(pills[0].getAttribute("style") ?? "", new RegExp(approved.surface, "i"));
    assert.match(pills[0].querySelector('[data-testid="status-dot"]')?.getAttribute("style") ?? "", new RegExp(approved.ink, "i"));
    assert.equal(pills.every((pill) => pill.querySelector('[data-testid="status-dot"]')), true);
    await page.close();
  });

  test("pill ink and the loading track clear their contrast floors", () => {
    for (const tone of Object.values(BUSINESS_STATUS)) {
      assert.ok(contrastRatio(tone.ink, tone.surface) >= 4.5, `${tone.label} ${contrastRatio(tone.ink, tone.surface)}`);
    }
    assert.ok(contrastRatio(LOADING_TRACK, "#ffffff") >= 3);
    assert.ok(contrastRatio(LOADING_TRACK, CANVAS) >= 3);
    assert.ok(contrastRatio("#ffffff", CONFIRM_ACTION) >= 4.5);
    const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
    assert.match(css, /--cuadrao-cream:\s*#F7F5EE/);
    assert.match(css, /border-color:\s*#7d8a84/);
  });

  test("the empty Bandeja uses the locked sentence", async () => {
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    assert.equal(spanish.business.inbox.empty_body, "Sube un recibo o envíalo por WhatsApp. Te esperará aquí para que lo revises.");
  });
});

describe("one toast at a time", () => {
  test("a queue shows the first notice, then the next, and undo waits longer", async () => {
    const pending: { fn: () => void; ms: number }[] = [];
    const real = window.setTimeout;
    window.setTimeout = ((fn: TimerHandler, ms?: number, ...args: unknown[]) => {
      if ((ms === PLAIN_TOAST_MS || ms === UNDO_TOAST_MS) && typeof fn === "function") {
        pending.push({ fn, ms });
        return pending.length as unknown as ReturnType<typeof setTimeout>;
      }
      return real(fn as never, ms as number, ...args);
    }) as typeof setTimeout;
    try {
      const { ToastQueue } = await import("@/components/business-app/foundation/ToastNotice");
      function Queue() {
        const [items, setItems] = useState([
          { text: "Guardado", kind: "confirm" as const },
          { text: "Deshecho", kind: "undo" as const, onUndo: () => undefined },
        ]);
        return <ToastQueue items={items} onDismiss={() => setItems((current) => current.slice(1))} />;
      }
      const page = await render(<Queue />);
      assert.equal(page.host.querySelectorAll('[data-testid="undo-toast"]').length, 1);
      assert.match(page.host.textContent ?? "", /Guardado/);
      assert.equal((page.host.textContent ?? "").includes("Deshecho"), false);
      assert.equal(page.host.querySelector('[data-testid="undo-toast"]')?.getAttribute("data-toast-kind"), "confirm");
      assert.equal(pending[0]?.ms, PLAIN_TOAST_MS);
      await page.act(async () => { pending[0].fn(); });
      assert.match(page.host.textContent ?? "", /Deshecho/);
      assert.equal((page.host.textContent ?? "").includes("Guardado"), false);
      assert.equal(pending.at(-1)?.ms, UNDO_TOAST_MS);
      await page.close();
    } finally {
      window.setTimeout = real;
    }
  });

  test("an undo toast stays longer and pauses while the pointer is over it", async () => {
    const pending: { fn: () => void; ms: number }[] = [];
    const real = window.setTimeout;
    window.setTimeout = ((fn: TimerHandler, ms?: number, ...args: unknown[]) => {
      if (ms === UNDO_TOAST_MS && typeof fn === "function") {
        pending.push({ fn, ms });
        return pending.length as unknown as ReturnType<typeof setTimeout>;
      }
      return real(fn as never, ms as number, ...args);
    }) as typeof setTimeout;
    try {
      const { ToastNotice } = await import("@/components/business-app/foundation/ToastNotice");
      const page = await render(<ToastNotice text="Marcado" kind="undo" onUndo={() => undefined} onClose={() => undefined} />);
      assert.equal(pending.length, 1);
      assert.equal(pending[0].ms, UNDO_TOAST_MS);
      const notice = page.host.querySelector('[data-testid="undo-toast"]') as HTMLElement;
      await page.act(async () => { notice.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); });
      const parked = pending.length;
      await page.act(async () => { notice.dispatchEvent(new MouseEvent("mouseout", { bubbles: true })); });
      assert.equal(pending.length, parked + 1);
      await page.close();
    } finally {
      window.setTimeout = real;
    }
  });
});

describe("Ver más uncovers rows and Cargar más asks for more", () => {
  test("reveal does not fetch, a failed fetch keeps the rows and offers Reintentar", async () => {
    const { ListPager } = await import("@/components/business-app/foundation/ListPager");
    const loads: string[] = [];
    function Harness({ loadState }: { loadState: "idle" | "error" }) {
      return (
        <ListPager
          items={["a", "b", "c"]}
          pageSize={1}
          load={() => loads.push(loadState)}
          loadState={loadState}
          revealLabel="Ver más"
          loadLabel="Cargar más"
          retryLabel="Reintentar"
          renderItem={(item) => <li key={item}>{item}</li>}
        />
      );
    }
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => { root.render(<Harness loadState="idle" />); });
    assert.deepEqual([...host.querySelectorAll("li")].map((row) => row.textContent), ["a"]);
    assert.equal(host.querySelector('[data-testid="list-load"]'), null);
    await act(async () => { (host.querySelector('[data-testid="list-reveal"]') as HTMLButtonElement).click(); });
    assert.deepEqual([...host.querySelectorAll("li")].map((row) => row.textContent), ["a", "b"]);
    assert.deepEqual(loads, []);
    await act(async () => { (host.querySelector('[data-testid="list-reveal"]') as HTMLButtonElement).click(); });
    const load = host.querySelector('[data-testid="list-load"]') as HTMLButtonElement;
    assert.equal(load.textContent, "Cargar más");
    await act(async () => load.click());
    assert.deepEqual(loads, ["idle"]);
    await act(async () => { root.render(<Harness loadState="error" />); });
    assert.deepEqual([...host.querySelectorAll("li")].map((row) => row.textContent), ["a", "b", "c"]);
    const retry = host.querySelector('[data-testid="list-retry"]') as HTMLButtonElement;
    assert.equal(retry.textContent, "Reintentar");
    assert.equal(host.querySelector('[data-testid="list-load"]'), null);
    await act(async () => retry.click());
    assert.deepEqual(loads, ["idle", "error"]);
    await act(async () => { root.unmount(); host.remove(); });
  });
});

describe("the delete confirmation", () => {
  test("the confirm names the record, accepts one press, and returns focus", async () => {
    const { ConfirmDialog } = await import("@/components/ui/ConfirmDialog");
    const presses: number[] = [];
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" data-testid="delete-opener" onClick={() => setOpen(true)}>Eliminar Ferretería La Esquina</button>
          <ConfirmDialog
            isOpen={open}
            title="Eliminar Ferretería La Esquina"
            description="Se quita Ferretería La Esquina."
            confirmLabel="Eliminar"
            cancelLabel="Cancelar"
            onCancel={() => setOpen(false)}
            onConfirm={() => { presses.push(1); setOpen(false); }}
          />
        </>
      );
    }
    const page = await render(<Harness />);
    const opener = page.host.querySelector('[data-testid="delete-opener"]') as HTMLButtonElement;
    opener.focus();
    await page.act(async () => opener.click());
    const dialog = document.querySelector('[role="alertdialog"]');
    assert.match(dialog?.textContent ?? "", /Ferretería La Esquina/);
    const confirm = document.querySelector('[data-testid="confirm-dialog-confirm"]') as HTMLButtonElement;
    assert.match(confirm.getAttribute("style") ?? "", /#9e2f39/i);
    await page.act(async () => { confirm.click(); confirm.click(); });
    assert.deepEqual(presses, [1]);
    assert.equal(document.querySelector('[role="alertdialog"]'), null);
    assert.equal(document.activeElement, opener);
    await page.close();
  });
});

describe("phone navigation", () => {
  test("the phone header is the mark and Buscar, with no menu button", async () => {
    const { PhoneSearchButton } = await import("@/components/business-app/foundation/BusinessPhoneHeader");
    const opened: number[] = [];
    const page = await render(
      <>
        <span data-testid="business-mark">M</span>
        <PhoneSearchButton label="Buscar" onSearch={() => opened.push(1)} />
      </>,
    );
    assert.equal(page.host.querySelector('[data-testid="chat-shell-menu-trigger"]'), null);
    assert.equal(page.host.querySelector('[data-testid="business-mark"]')?.textContent, "M");
    const search = page.host.querySelector('[data-testid="business-phone-search"]') as HTMLButtonElement;
    assert.equal(search.getAttribute("aria-label"), "Buscar");
    assert.ok(search.querySelector("svg"));
    await page.act(async () => search.click());
    assert.deepEqual(opened, [1]);
    await page.close();
  });
});
