import { afterEach, beforeAll, expect, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import i18next from "i18next";
import { act, createElement, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { I18nextProvider } from "react-i18next";

// The front door with a held one-time-code request and a held language save,
// so an exit the user chooses mid-flight can be observed against the
// navigation the late completion would have made.
const navigations: string[] = [];
mock.module("next/navigation", () => ({
  useRouter: () => ({
    push: (href: string) => { navigations.push(`push ${href}`); },
    replace: (href: string) => { navigations.push(`replace ${href}`); },
    refresh: () => { navigations.push("refresh"); },
    prefetch: () => undefined,
  }),
  useSearchParams: () => new URLSearchParams(window.location.search),
  usePathname: () => "/",
}));

const gate = () => {
  let open: () => void = () => {};
  const promise = new Promise<void>((resolve) => { open = resolve; });
  return { promise, open: () => open() };
};
let verifyGate = gate();
let patchGate = gate();
const account = { id: "user-1", email: "ada@example.com", language: "es-419", locale: "es-419" };

mock.module("@/lib/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: {
      verifyOtp: async () => { await verifyGate.promise; return { data: { user: account, session: {} }, error: null }; },
    },
  }),
}));
const realApi = await import("@/lib/argus-api");
mock.module("@/lib/argus-api", () => ({
  ...realApi,
  signupWithEmail: async () => ({ response: { user: account, session: null }, needsEmailConfirmation: true }),
  patchMe: async () => { await patchGate.promise; return { user: account }; },
}));

const { default: LandingPage } = await import("@/app/page");
const es419 = (await import("@/public/locales/es-419/common.json")).default;
const en = (await import("@/public/locales/en/common.json")).default;

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/?auth=signup" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

let mounted: { root: Root; host: HTMLElement } | null = null;
afterEach(async () => {
  await act(async () => { mounted?.root.unmount(); });
  mounted?.host.remove();
  mounted = null;
  navigations.length = 0;
  verifyGate = gate();
  patchGate = gate();
  window.history.replaceState(null, "", "/?auth=signup");
});

async function setNativeValue(element: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  await act(async () => {
    setter?.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function openFrontDoor() {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: "es-419",
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: { "es-419": { translation: es419 }, en: { translation: en } },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  mounted = { root, host };
  await act(async () => {
    root.render(createElement(I18nextProvider, { i18n }, createElement(LandingPage) as ReactNode));
  });
  for (let attempt = 0; attempt < 20 && !host.querySelector("[data-auth-brand]"); attempt += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)); });
  }
  if (!host.querySelector("[data-auth-brand]")) throw new Error("front door did not settle");
  return host;
}

async function submit(host: HTMLElement) {
  const form = host.querySelector("form") as HTMLFormElement;
  await act(async () => { form.requestSubmit(form.querySelector("button[type='submit']") as HTMLButtonElement); });
}

async function reachCheckEmail(host: HTMLElement) {
  await setNativeValue(host.querySelector('input[type="email"]') as HTMLInputElement, "ada@example.com");
  await submit(host);
  await setNativeValue(host.querySelector('input[autocomplete="new-password"]') as HTMLInputElement, "correct-horse-battery");
  await submit(host);
  expect(host.querySelector("[data-testid='auth-check-email']")).not.toBeNull();
  await setNativeValue(host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement, "01234567");
  await submit(host);
}

function chooseSignIn(host: HTMLElement) {
  const signIn = host.querySelector("[data-testid='auth-check-email-exits'] button") as HTMLButtonElement;
  expect(signIn.disabled).toBe(false);
  return act(async () => { signIn.click(); });
}

function expectLoginView(host: HTMLElement) {
  expect(host.querySelector("[data-testid='auth-check-email']")).toBeNull();
  expect(new URLSearchParams(window.location.search).get("auth")).toBe("login");
  expect((host.querySelector('input[type="email"]') as HTMLInputElement).value).toBe("ada@example.com");
}

test("sign-in chosen while the code is being checked: the late success does not leave the sign-in path", async () => {
  const host = await openFrontDoor();
  await reachCheckEmail(host);
  await chooseSignIn(host);
  expectLoginView(host);

  await act(async () => { verifyGate.open(); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(navigations).toEqual([]);
  expectLoginView(host);
});

test("sign-in chosen while the confirmed signup is still saving the chosen language: no navigation", async () => {
  const host = await openFrontDoor();
  const english = host.querySelector("[data-testid='auth-language-switch'] button[lang='en']") as HTMLButtonElement;
  await act(async () => { english.click(); });
  verifyGate.open();
  await reachCheckEmail(host);
  expect(host.querySelector("[data-otp-status]")?.getAttribute("data-otp-status")).toBe("verified");
  await chooseSignIn(host);
  expectLoginView(host);

  await act(async () => { patchGate.open(); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(navigations).toEqual([]);
  expectLoginView(host);
});

test("with no exit chosen, the confirmed signup still goes to the signed-in home", async () => {
  const host = await openFrontDoor();
  const english = host.querySelector("[data-testid='auth-language-switch'] button[lang='en']") as HTMLButtonElement;
  await act(async () => { english.click(); });
  verifyGate.open();
  await reachCheckEmail(host);

  await act(async () => { patchGate.open(); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(navigations).toEqual(["replace /biz", "refresh"]);
});
