import { afterAll, afterEach, beforeAll, describe, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { RefreshOutcome } from "@/components/ui/pull-to-refresh";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 390, height: 844 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

type Device = { phone: boolean; coarse: boolean; reduced: boolean };
const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  document.body.innerHTML = "";
});

function emulateDevice(device: Device) {
  const answers = (query: string) =>
    query.includes("pointer: coarse") ? device.coarse : query.includes("prefers-reduced-motion") ? device.reduced : query.includes("max-width") ? device.phone : false;
  window.matchMedia = ((query: string) => ({
    matches: answers(query), media: query, onchange: null,
    addEventListener: () => undefined, removeEventListener: () => undefined, addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

const later = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function mount(device: Device, onRefresh: () => Promise<RefreshOutcome>) {
  emulateDevice(device);
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { PullToRefresh } = await import("@/components/ui/PullToRefresh");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  host.style.overflowY = "auto";
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <PullToRefresh onRefresh={onRefresh}>
        <ul><li data-testid="row">Fila</li><li><div data-testid="sideways" style={{ overflowX: "auto" }}>Bandeja lateral</div></li></ul>
      </PullToRefresh>
    </I18nextProvider>,
  ));
  unmounts.push(async () => { await act(async () => root.unmount()); });
  const surface = host.querySelector<HTMLElement>('[data-testid="pull-to-refresh"]')!;
  const row = host.querySelector<HTMLElement>('[data-testid="row"]')!;
  const content = surface.lastElementChild as HTMLElement;
  const touch = (type: string, target: HTMLElement, x: number, y: number) => {
    const point = new Touch({ identifier: 1, target, clientX: x, clientY: y });
    const event = new TouchEvent(type, { touches: type === "touchend" ? [] : [point], changedTouches: [point], bubbles: true, cancelable: true });
    target.dispatchEvent(event);
    return event;
  };
  /** A finger from y=100 down by `travel` in small steps; the last move's event is returned. */
  const pull = async (travel: number, { target = row, dx = 0, release = true } = {}) => {
    let last: TouchEvent | null = null;
    await act(async () => {
      touch("touchstart", target, 100, 100);
      for (let step = 1; step <= 10; step += 1) last = touch("touchmove", target, 100 + (dx * step) / 10, 100 + (travel * step) / 10);
    });
    if (release) await act(async () => { touch("touchend", target, 100 + dx, 100 + travel); });
    return last as unknown as TouchEvent;
  };
  return {
    act, host, surface, content, pull,
    phase: () => surface.dataset.phase,
    said: () => host.querySelector('[data-testid="pull-announcement"]')?.textContent ?? null,
  };
}

const PHONE: Device = { phone: true, coarse: true, reduced: false };

describe("pull to refresh on a phone list", () => {
  test("a pull past the threshold at the top runs the list's reload once, holds until it answers, then says Actualizado", async () => {
    let calls = 0;
    let answer: (outcome: RefreshOutcome) => void = () => undefined;
    const screen = await mount(PHONE, () => { calls += 1; return new Promise((resolve) => { answer = resolve; }); });
    const last = await screen.pull(240);
    expect(last.defaultPrevented).toBe(true);
    expect(calls).toBe(1);
    expect(screen.phase()).toBe("refreshing");
    expect(screen.content.getAttribute("aria-busy")).toBe("true");
    await screen.act(async () => { await later(400); });
    expect(screen.phase()).toBe("refreshing");
    // Another release while it runs is not a second reload.
    await screen.pull(240);
    expect(calls).toBe(1);
    await screen.act(async () => { answer("updated"); await later(0); });
    expect(screen.phase()).toBe("settling");
    expect(screen.said()).toBe("Actualizado");
    await screen.act(async () => { await later(260); });
    expect(screen.phase()).toBe("idle");
    expect(screen.content.style.transform).toBe("");
    await screen.pull(240);
    expect(calls).toBe(2);
  });

  test("a failed reload says so politely and comes back to rest", async () => {
    const screen = await mount(PHONE, async () => "failed");
    await screen.pull(240);
    await screen.act(async () => { await later(0); });
    expect(screen.said()).toBe("No pudimos actualizar.");
    await screen.act(async () => { await later(260); });
    expect(screen.phase()).toBe("idle");
  });

  test("a release short of the threshold springs back and never reloads", async () => {
    let calls = 0;
    const screen = await mount(PHONE, async () => { calls += 1; return "updated"; });
    await screen.pull(60);
    expect(screen.phase()).toBe("settling");
    await screen.act(async () => { await later(260); });
    expect(screen.phase()).toBe("idle");
    expect(calls).toBe(0);
  });

  test("with the list scrolled down a pull is the list's scroll: nothing is held or reloaded", async () => {
    let calls = 0;
    const screen = await mount(PHONE, async () => { calls += 1; return "updated"; });
    screen.host.scrollTop = 120;
    const last = await screen.pull(240);
    expect(last.defaultPrevented).toBe(false);
    expect(screen.phase()).toBe("idle");
    expect(calls).toBe(0);
  });

  test("sideways travel belongs to the row or tray under the finger and is never held", async () => {
    let calls = 0;
    const screen = await mount(PHONE, async () => { calls += 1; return "updated"; });
    const sideways = screen.host.querySelector<HTMLElement>('[data-testid="sideways"]')!;
    const last = await screen.pull(60, { target: sideways, dx: 200 });
    expect(last.defaultPrevented).toBe(false);
    expect(screen.phase()).toBe("idle");
    expect(calls).toBe(0);
  });

  test("a gesture the browser takes away springs back and never reloads", async () => {
    let calls = 0;
    const screen = await mount(PHONE, async () => { calls += 1; return "updated"; });
    await screen.pull(240, { release: false });
    expect(screen.phase()).toBe("armed");
    await screen.act(async () => { screen.host.querySelector('[data-testid="row"]')!.dispatchEvent(new TouchEvent("touchcancel", { touches: [], bubbles: true })); });
    expect(screen.phase()).toBe("settling");
    expect(calls).toBe(0);
  });

  test("with reduced motion the content never moves; the reload still runs", async () => {
    let calls = 0;
    const screen = await mount({ ...PHONE, reduced: true }, async () => { calls += 1; return "updated"; });
    await screen.pull(240, { release: false });
    expect(screen.phase()).toBe("armed");
    expect(screen.content.style.transform).toBe("");
    await screen.act(async () => { screen.host.querySelector('[data-testid="row"]')!.dispatchEvent(new TouchEvent("touchend", { touches: [], bubbles: true })); });
    expect(calls).toBe(1);
    expect(screen.content.style.transform).toBe("");
  });

  test("the motion pull moves the content with the finger", async () => {
    const screen = await mount(PHONE, async () => "updated");
    await screen.pull(100, { release: false });
    expect(screen.content.style.transform).toContain("translate3d(0");
  });
});

describe("pull to refresh elsewhere", () => {
  for (const [name, device] of [["a desktop", { phone: false, coarse: false, reduced: false }], ["a phone width with a mouse", { phone: true, coarse: false, reduced: false }], ["a tablet with touch", { phone: false, coarse: true, reduced: false }]] as const) {
    test(`${name} renders the list and does nothing on a pull`, async () => {
      let calls = 0;
      const screen = await mount(device, async () => { calls += 1; return "updated"; });
      const last = await screen.pull(240);
      expect(last.defaultPrevented).toBe(false);
      expect(screen.phase()).toBe("idle");
      expect(calls).toBe(0);
      expect(screen.host.querySelector('[data-testid="pull-indicator"]')).toBeNull();
      expect(screen.host.querySelector('[data-testid="row"]')?.textContent).toBe("Fila");
    });
  }
});
