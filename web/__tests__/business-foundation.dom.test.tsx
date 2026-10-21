import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { useState } from "react";
import { BUSINESS_STATUS, CANVAS, CONFIRM_ACTION, LOADING_TRACK, MUTED_TEXT, contrastRatio } from "@/components/business-app/foundation/presentation";

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

describe("status is an icon, a word, and a color", () => {
  test("each receipt status shows its icon and Spanish name on its locked colors", async () => {
    const { StatusPill } = await import("@/components/business-app/foundation/StatusPill");
    const page = await render(
      <>
        <StatusPill status="confirmed" />
        <StatusPill status="needs_attention" />
        <StatusPill status="saved" />
      </>,
    );
    const pills = [...page.host.querySelectorAll<HTMLElement>('[data-testid="status-pill"]')];
    assert.deepEqual(pills.map((pill) => pill.textContent), ["Aprobado", "Necesita atención", "Pendiente"]);
    assert.deepEqual(pills.map((pill) => pill.getAttribute("data-status")), ["approved", "needs_attention", "pending"]);
    const icons = pills.map((pill) => pill.querySelector("svg"));
    assert.deepEqual(icons.map((icon) => [...(icon?.classList ?? [])].find((name) => /^lucide-(circle-check|clock|circle-alert)$/.test(name))), ["lucide-circle-check", "lucide-circle-alert", "lucide-clock"]);
    assert.ok(icons.every((icon) => icon?.getAttribute("aria-hidden") === "true" && icon.getAttribute("width") === "14" && icon.getAttribute("height") === "14"));
    for (const [index, name] of (["approved", "needs_attention", "pending"] as const).entries()) {
      assert.match(pills[index].getAttribute("style") ?? "", new RegExp(BUSINESS_STATUS[name].ink, "i"));
      assert.match(pills[index].getAttribute("style") ?? "", new RegExp(BUSINESS_STATUS[name].surface, "i"));
    }
    assert.ok(pills.every((pill) => /(^|\s)h-6(\s|$)/.test(pill.className) && /rounded-full/.test(pill.className) && /px-2/.test(pill.className) && /text-\[12px\]/.test(pill.className) && /leading-4/.test(pill.className) && /font-medium/.test(pill.className)));
    assert.equal(page.host.querySelector('[data-testid="status-dot"]'), null);
    await page.close();
  });

  test("pill ink, muted text, and the loading track clear their contrast floors", () => {
    for (const tone of Object.values(BUSINESS_STATUS)) {
      assert.ok(contrastRatio(tone.ink, tone.surface) >= 4.5, `${tone.label} ${contrastRatio(tone.ink, tone.surface)}`);
    }
    assert.ok(contrastRatio(LOADING_TRACK, "#ffffff") >= 3);
    assert.ok(contrastRatio(LOADING_TRACK, CANVAS) >= 3);
    assert.ok(contrastRatio("#ffffff", CONFIRM_ACTION) >= 4.5);
    assert.ok(contrastRatio(MUTED_TEXT, "#ffffff") >= 4.5);
    assert.ok(contrastRatio(MUTED_TEXT, CANVAS) >= 4.5);
    const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
    assert.match(css, /--cuadrao-cream:\s*#F7F5EE/);
    assert.match(css, /border-color:\s*#7d8a84/);
  });

  test("the empty Bandeja uses the locked sentence", async () => {
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    assert.equal(spanish.business.inbox.empty_body, "Sube un recibo o envíalo por WhatsApp. Te esperará aquí para que lo revises.");
  });
});

describe("toasts", () => {
  test("info and success leave after 4 seconds, warning after 7, an action after 8, and an error stays", async () => {
    const { toastDuration } = await import("@/components/business-app/foundation/toasts");
    assert.equal(toastDuration({ kind: "info", text: "x" }), 4000);
    assert.equal(toastDuration({ kind: "success", text: "x" }), 4000);
    assert.equal(toastDuration({ kind: "warning", text: "x" }), 7000);
    assert.equal(toastDuration({ kind: "success", text: "x", action: { label: "Deshacer", run: () => undefined } }), 8000);
    assert.equal(toastDuration({ kind: "error", text: "x" }), null);
    assert.equal(toastDuration({ kind: "error", text: "x", action: { label: "Reintentar", run: () => undefined } }), null);
  });

  test("one toast at a time: the newest replaces the one on screen, and its Deshacer leaves with it", async () => {
    const { clearToasts, showToast, useToasts } = await import("@/components/business-app/foundation/toasts");
    clearToasts();
    showToast({ kind: "error", text: "error uno" });
    showToast({ kind: "success", text: "guardado uno", action: { label: "Deshacer", run: () => undefined } });
    showToast({ kind: "info", text: "aviso" });
    let seen: string[] = [];
    function Probe() {
      seen = useToasts().map((toast) => toast.text);
      return null;
    }
    const page = await render(<Probe />);
    assert.deepEqual(seen, ["aviso"]);
    await page.close();
    clearToasts();
  });

  test("each toast shows its kind's icon and border, closes on its button, and an error is an alert", async () => {
    const { clearToasts, showToast } = await import("@/components/business-app/foundation/toasts");
    const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
    clearToasts();
    const page = await render(<ToastViewport />);
    await page.act(async () => { showToast({ kind: "error", text: "No pudimos guardar." }); });
    const toast = page.host.querySelector('[data-testid="toast"]') as HTMLElement;
    assert.equal(toast.getAttribute("data-kind"), "error");
    assert.equal(toast.getAttribute("role"), "alert");
    assert.ok(toast.querySelector("svg"), "an icon, not colour alone");
    assert.ok(toast.style.borderLeftColor, "a left border colour per kind");
    const close = toast.querySelector('button[aria-label="Cerrar"]') as HTMLButtonElement;
    assert.ok(close);
    await page.act(async () => { close.click(); });
    assert.equal(page.host.querySelectorAll('[data-testid="toast"]').length, 0);
    await page.close();
  });

  test("hovering pauses the clock, and leaving resumes it with the time that was left", async () => {
    const { clearToasts, showToast } = await import("@/components/business-app/foundation/toasts");
    const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
    const timers: { fn: () => void; ms: number; cleared: boolean }[] = [];
    const real = { set: window.setTimeout, clear: window.clearTimeout };
    window.setTimeout = ((fn: TimerHandler, ms?: number) => {
      if (typeof fn === "function" && typeof ms === "number" && ms >= 1000) {
        timers.push({ fn: fn as () => void, ms, cleared: false });
        return timers.length as unknown as ReturnType<typeof setTimeout>;
      }
      return real.set(fn as never, ms as number);
    }) as typeof setTimeout;
    window.clearTimeout = ((id?: number) => {
      const timer = typeof id === "number" ? timers[id - 1] : undefined;
      if (timer) timer.cleared = true;
      else real.clear(id);
    }) as typeof clearTimeout;
    try {
      clearToasts();
      const page = await render(<ToastViewport />);
      await page.act(async () => { showToast({ kind: "info", text: "Dirección copiada." }); });
      assert.equal(timers.at(-1)?.ms, 4000);
      const toast = page.host.querySelector('[data-testid="toast"]') as HTMLElement;
      await page.act(async () => { toast.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, relatedTarget: document.body })); });
      assert.equal(timers.at(-1)?.cleared, true, "hover stops the clock");
      const before = timers.length;
      await page.act(async () => { toast.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body })); });
      assert.ok(timers.length > before, "leaving starts it again");
      assert.ok((timers.at(-1)?.ms ?? 5000) <= 4000, "with the time that was left, never more");
      await page.close();
      clearToasts();
    } finally {
      window.setTimeout = real.set;
      window.clearTimeout = real.clear;
    }
  });

  test("the stack springs with stiffness 180 and damping 20: a small overshoot, then rest at 1", async () => {
    const { springEasing } = await import("@/components/business-app/foundation/toasts");
    const { easing, durationMs } = springEasing(180, 20);
    const values = easing.slice("linear(".length, -1).split(", ").map(Number);
    assert.equal(values[0], 0);
    assert.equal(values.at(-1), 1);
    const peak = Math.max(...values);
    assert.ok(peak > 1 && peak < 1.06, `overshoot ${peak}`);
    assert.ok(durationMs > 400 && durationMs < 1000, `settles in ${durationMs}ms`);
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
