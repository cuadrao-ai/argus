import { afterAll, afterEach, beforeAll, beforeEach, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import { AuthHero } from "../components/auth/AuthHero";
import AuthForm from "../components/auth/AuthForm";
import { useTypewriter } from "../components/ui/useTypewriter";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

let host: HTMLDivElement;
let root: Root;
let reduceMotion = false;
let nextTimer = 1;
const timers = new Map<number, () => void>();
const motionListeners = new Set<() => void>();
let restore: () => void;

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  reduceMotion = false;
  timers.clear();
  motionListeners.clear();
  const original = { interval: window.setInterval, clear: window.clearInterval, media: window.matchMedia };
  window.setInterval = ((callback: () => void) => {
    const id = nextTimer++;
    timers.set(id, callback);
    return id;
  }) as typeof window.setInterval;
  window.clearInterval = ((id: number) => { timers.delete(id); }) as typeof window.clearInterval;
  window.matchMedia = (() => ({
    get matches() { return reduceMotion; },
    addEventListener: (_: string, listener: () => void) => motionListeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => motionListeners.delete(listener),
  })) as unknown as typeof window.matchMedia;
  restore = () => {
    window.setInterval = original.interval;
    window.clearInterval = original.clear;
    window.matchMedia = original.media;
  };
});
afterEach(async () => {
  await act(async () => root.unmount());
  restore();
  host.remove();
});
async function tick(count = 1) {
  for (let i = 0; i < count; i++) {
    await act(async () => { for (const callback of [...timers.values()]) callback(); });
  }
}
function Probe({ text }: { text: string }) {
  const { visibleCount, done } = useTypewriter(text);
  return <p data-done={done}>{text.slice(0, visibleCount)}</p>;
}

test("shared typewriter completes once, ignores rerenders, and cleans up on text changes and unmount", async () => {
  await act(async () => root.render(<Probe text="Hello" />));
  await tick(2);
  expect(host.textContent).toBe("He");
  await act(async () => root.render(<Probe text="Hello" />));
  expect(host.textContent).toBe("He");
  expect(timers.size).toBe(1);
  await tick(10);
  expect(host.textContent).toBe("Hello");
  expect(timers.size).toBe(0);
  await act(async () => root.render(<Probe text="Hello" />));
  expect(host.textContent).toBe("Hello");
  expect(timers.size).toBe(0);
  await act(async () => root.render(<Probe text="Hola" />));
  expect(host.textContent).toBe("");
  await tick();
  expect(host.textContent).toBe("H");
  await act(async () => root.render(null));
  expect(timers.size).toBe(0);
  expect(motionListeners.size).toBe(0);
});

test("reduced motion shows the full phrase immediately and cancels an active animation", async () => {
  reduceMotion = true;
  await act(async () => root.render(<Probe text="Hola" />));
  expect(host.textContent).toBe("Hola");
  expect(timers.size).toBe(0);
  reduceMotion = false;
  await act(async () => root.render(<Probe text="Hello" />));
  await tick();
  reduceMotion = true;
  await act(async () => { for (const listener of motionListeners) listener(); });
  expect(host.textContent).toBe("Hello");
  expect(timers.size).toBe(0);
});

const copy = [
  ["es-419", "signup", "Tus cuentas en orden.", "Crea tu cuenta"],
  ["en", "signup", "Your finances in order.", "Create your account"],
  ["es-419", "login", "Todo en su sitio. Sigamos.", "Inicia sesión"],
  ["en", "login", "Everything in place. Pick up where you left off.", "Sign in"],
] as const;

test.each(copy)("%s %s keeps complete hero accessible and form title static", async (language, mode, hero, title) => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, fallbackLng: false, resources: { en: { translation: en }, "es-419": { translation: es } } });
  const render = () => createElement(I18nextProvider, { i18n }, <><AuthHero mode={mode} /><AuthForm mode={mode} onSubmit={async () => {}} /></>);
  await act(async () => root.render(render()));
  const heading = host.querySelector('[data-testid="auth-hero"]')!;
  expect(heading.querySelector(".sr-only")?.textContent).toBe(hero);
  expect(heading.querySelector('[aria-hidden="true"]')?.textContent?.replaceAll("\n", " ")).toBe(hero);
  expect(heading.querySelectorAll(".invisible").length).toBe(hero.length);
  expect(heading.querySelector("[aria-live], [role=status]")).toBeNull();
  expect(host.querySelectorAll("h2")[1]?.textContent).toBe(title);
  expect(host.querySelector("input")?.disabled).toBe(false);
  await tick(2);
  expect(heading.querySelectorAll(".visible").length).toBe(2);
  await act(async () => root.render(render()));
  expect(heading.querySelectorAll(".visible").length).toBe(2);
  await tick(hero.length);
  expect(heading.querySelectorAll(".invisible").length).toBe(0);
  expect(timers.size).toBe(0);
  await act(async () => i18n.changeLanguage(language === "en" ? "es-419" : "en"));
  expect(host.querySelectorAll('[data-testid="auth-hero"] .invisible').length).toBe(0);
  expect(timers.size).toBe(0);
});
