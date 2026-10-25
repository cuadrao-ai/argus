import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, beforeEach, setSystemTime, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToString } from "react-dom/server";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import HomeGreeting from "@/components/business-app/foundation/HomeGreeting";
import BusinessHeader from "@/components/business-app/foundation/BusinessHeader";
import { greetingPeriod, nextGreetingBoundary, useHomeClock, type GreetingPeriod } from "@/components/business-app/foundation/home-greeting";
import { readSessionStored, removeSessionStored } from "@/lib/browser-storage";
import en from "@/public/locales/en/common.json";
import es from "@/public/locales/es-419/common.json";

let host: HTMLDivElement;
let root: Root;
let reduced = false;
let visibility: DocumentVisibilityState = "visible";
let restore: () => void;
let nextTimer = 0;
const intervals = new Map<number, () => void>();
const timeouts = new Map<number, { callback: () => void; delay: number }>();

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  reduced = false;
  visibility = "visible";
  intervals.clear();
  timeouts.clear();
  removeSessionStored("cuadrao:home-greeting-seen");
  setSystemTime(new Date(2026, 9, 25, 7));
  const original = { interval: window.setInterval, clearInterval: window.clearInterval, timeout: window.setTimeout, clearTimeout: window.clearTimeout, media: window.matchMedia, visibility: Object.getOwnPropertyDescriptor(document, "visibilityState") };
  window.setInterval = ((callback: () => void) => { intervals.set(++nextTimer, callback); return nextTimer; }) as typeof window.setInterval;
  window.clearInterval = ((id: number) => { intervals.delete(id); }) as typeof window.clearInterval;
  window.setTimeout = ((callback: () => void, delay: number) => { timeouts.set(++nextTimer, { callback, delay }); return nextTimer; }) as typeof window.setTimeout;
  window.clearTimeout = ((id: number) => { timeouts.delete(id); }) as typeof window.clearTimeout;
  window.matchMedia = (() => ({ get matches() { return reduced; }, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
  restore = () => {
    Object.assign(window, { setInterval: original.interval, clearInterval: original.clearInterval, setTimeout: original.timeout, clearTimeout: original.clearTimeout, matchMedia: original.media });
    if (original.visibility) Object.defineProperty(document, "visibilityState", original.visibility);
    else delete (document as unknown as Record<string, unknown>).visibilityState;
    setSystemTime();
  };
});
afterEach(async () => { await act(async () => root.unmount()); restore(); host.remove(); });

async function translation(language = "es-419") {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { en: { translation: en }, "es-419": { translation: es } }, interpolation: { escapeValue: false } });
  return i18n;
}
const state = () => host.querySelector("[data-greeting-state]")?.getAttribute("data-greeting-state");
const accessibleText = () => host.querySelector(".sr-only")?.textContent ?? host.textContent;
async function tick(count = 1) {
  for (let index = 0; index < count; index++) await act(async () => { for (const callback of [...intervals.values()]) callback(); });
}

test("local hour boundaries use all four approved periods", () => {
  for (const [hour, period] of [[0, "late_night"], [4, "late_night"], [5, "morning"], [11, "morning"], [12, "afternoon"], [17, "afternoon"], [18, "evening"], [22, "evening"], [23, "late_night"]] as const) assert.equal(greetingPeriod(hour), period);
  assert.equal(nextGreetingBoundary(new Date(2026, 9, 25, 11, 59, 59)).getTime(), new Date(2026, 9, 25, 12).getTime());
  assert.equal(nextGreetingBoundary(new Date(2026, 9, 25, 23, 59, 59)).getTime(), new Date(2026, 9, 26).getTime());
});

test("both languages use approved copy, with comma and preferred name only when present", async () => {
  reduced = true;
  const periods: GreetingPeriod[] = ["morning", "afternoon", "evening", "late_night"];
  for (const [language, phrases] of [["es-419", ["Buenos días", "Buenas tardes", "Buenas noches", "Noche de enfoque"]], ["en", ["Good morning", "Good afternoon", "Good evening", "Late-night session"]]] as const) {
    const i18n = await translation(language);
    for (const [index, period] of periods.entries()) {
      for (const name of [null, "  ", " Ana "]) {
        await act(async () => root.render(<I18nextProvider i18n={i18n}><HomeGreeting period={period} name={name} /></I18nextProvider>));
        assert.equal(host.textContent, name?.trim() ? `${phrases[index]}, Ana` : phrases[index]);
        assert.equal(state(), "settled");
      }
    }
  }
  assert.equal(intervals.size, 0);
});

test("StrictMode first appearance types once with full accessible phrase and reserved characters", async () => {
  const i18n = await translation();
  const render = (period: GreetingPeriod = "morning", name = "Ana") => <StrictMode><I18nextProvider i18n={i18n}><HomeGreeting period={period} name={name} /></I18nextProvider></StrictMode>;
  await act(async () => root.render(render()));
  assert.equal(state(), "typing");
  assert.equal(readSessionStored("cuadrao:home-greeting-seen"), "1");
  assert.equal(accessibleText(), "Buenos días, Ana");
  assert.equal(host.querySelectorAll(".sr-only").length, 1);
  assert.equal(host.querySelector('[aria-hidden="true"]')?.textContent, "Buenos días, Ana");
  assert.equal(host.querySelectorAll(".invisible").length, "Buenos días, Ana".length);
  await tick(2);
  assert.equal(host.querySelectorAll(".visible").length, 2);
  await act(async () => root.render(render("afternoon", "Luisa")));
  assert.equal(state(), "settled");
  assert.equal(host.textContent, "Buenas tardes, Luisa");
  await act(async () => i18n.changeLanguage("en"));
  assert.equal(host.textContent, "Good afternoon, Luisa");
  await act(async () => { root.render(null); });
  await act(async () => root.render(render()));
  assert.equal(state(), "settled");
  assert.equal(intervals.size, 0);
});

test("a completed first greeting never replays, and reduced motion starts static", async () => {
  const i18n = await translation();
  await act(async () => root.render(<I18nextProvider i18n={i18n}><HomeGreeting period="morning" /></I18nextProvider>));
  await tick(30);
  assert.equal(state(), "settled");
  assert.equal(intervals.size, 0);
  await act(async () => root.render(null));
  removeSessionStored("cuadrao:home-greeting-seen");
  reduced = true;
  await act(async () => root.render(<I18nextProvider i18n={i18n}><HomeGreeting period="evening" /></I18nextProvider>));
  assert.equal(host.textContent, "Buenas noches");
  assert.equal(state(), "settled");
  assert.equal(intervals.size, 0);
});

test("leaving Home during typing does not replay it on remount", async () => {
  const i18n = await translation();
  const greeting = <I18nextProvider i18n={i18n}><HomeGreeting period="morning" /></I18nextProvider>;
  await act(async () => root.render(greeting));
  await tick(2);
  assert.equal(state(), "typing");
  await act(async () => root.render(null));
  assert.equal(intervals.size, 0);
  await act(async () => root.render(greeting));
  assert.equal(state(), "settled");
  assert.equal(host.textContent, "Buenos días");
  assert.equal(intervals.size, 0);
});

test("a hidden tab reserves the phrase without consuming its first visible appearance", async () => {
  visibility = "hidden";
  const i18n = await translation();
  await act(async () => root.render(<I18nextProvider i18n={i18n}><HomeGreeting period="morning" /></I18nextProvider>));
  assert.equal(state(), "pending");
  assert.equal(readSessionStored("cuadrao:home-greeting-seen"), null);
  assert.equal((host.querySelector('[aria-hidden="true"]') as HTMLElement).style.visibility, "hidden");
  visibility = "visible";
  await act(async () => document.dispatchEvent(new Event("visibilitychange")));
  assert.equal(state(), "typing");
});

test("clock refreshes at the boundary, midnight and resume; server renders no guessed local date", async () => {
  const i18n = await translation();
  const server = renderToString(<I18nextProvider i18n={i18n}><BusinessHeader home name={null} /></I18nextProvider>);
  assert.doesNotMatch(server, /Buenos días|2026-10-25/);
  function Clock() {
    const clock = useHomeClock();
    return <output>{clock ? `${clock.date.getDate()}:${clock.period}` : ""}</output>;
  }
  setSystemTime(new Date(2026, 9, 25, 11, 59, 59));
  await act(async () => root.render(<Clock />));
  assert.equal(host.textContent, "25:morning");
  assert.equal([...timeouts.values()][0].delay, 1000);
  setSystemTime(new Date(2026, 9, 25, 12));
  await act(async () => [...timeouts.values()][0].callback());
  assert.equal(host.textContent, "25:afternoon");
  setSystemTime(new Date(2026, 9, 25, 23, 59, 59));
  await act(async () => window.dispatchEvent(new Event("focus")));
  assert.equal(host.textContent, "25:late_night");
  setSystemTime(new Date(2026, 9, 26));
  await act(async () => [...timeouts.values()][0].callback());
  assert.equal(host.textContent, "26:late_night");
  setSystemTime(new Date(2026, 9, 26, 18));
  await act(async () => document.dispatchEvent(new Event("visibilitychange")));
  assert.equal(host.textContent, "26:evening");
});

test("denied session storage still prevents replay for the current page session", async () => {
  const i18n = await translation();
  const original = window.sessionStorage.setItem;
  window.sessionStorage.setItem = () => { throw new Error("Storage unavailable"); };
  try {
    const greeting = <I18nextProvider i18n={i18n}><HomeGreeting period="morning" /></I18nextProvider>;
    await act(async () => root.render(greeting));
    assert.equal(state(), "typing");
    await act(async () => root.render(null));
    await act(async () => root.render(greeting));
    assert.equal(state(), "settled");
    assert.equal(host.textContent, "Buenos días");
  } finally { window.sessionStorage.setItem = original; }
});
