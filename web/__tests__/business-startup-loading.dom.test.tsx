import { afterAll, afterEach, beforeAll, expect, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useEffect, useState, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import FullscreenLoading from "@/components/FullscreenLoading";
import spanish from "@/public/locales/es-419/common.json";

function ProfileGate() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    void fetch("/mock-profile").then(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, []);
  return ready ? <main data-testid="startup-home">Inicio</main> : <div data-testid="profile-startup" className="flex h-[100dvh]"><FullscreenLoading /></div>;
}

mock.module("@/components/business-app/BusinessWorkspace", () => ({ BusinessWorkspaceProvider: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/business-app/BusinessNamingProvider", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/chat/ChatInterface", () => ({ default: ProfileGate }));
mock.module("@/components/chat/ConversationShellGuard", () => ({ default: () => null }));
mock.module("@/components/business-app/ConversationUnavailableNotice", () => ({ default: () => null }));

const originalFetch = globalThis.fetch;
const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const i18n = i18next.createInstance();
const views: { host: HTMLElement; root: Root }[] = [];

beforeAll(async () => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
});
afterEach(async () => {
  for (const view of views.splice(0)) {
    await act(async () => view.root.unmount());
    view.host.remove();
  }
  globalThis.fetch = originalFetch;
});
afterAll(async () => {
  if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  await GlobalRegistrator.unregister();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function requests() {
  const directory = deferred<{ spaces: never[]; closed_spaces: never[] }>();
  const consent = deferred<{ version: string; accepted_at: string | null }>();
  const profile = deferred<void>();
  const calls: string[] = [];
  globalThis.fetch = async (input) => {
    const path = new URL(String(input), "http://localhost").pathname;
    calls.push(path);
    if (path.endsWith("/spaces")) return Response.json(await directory.promise);
    if (path.endsWith("/consent")) return Response.json(await consent.promise);
    if (path === "/mock-profile") { await profile.promise; return Response.json({}); }
    throw new Error(`Unexpected request ${path}`);
  };
  return { directory, consent, profile, calls };
}

async function mount() {
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  views.push({ host, root });
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessApp /></I18nextProvider>));
  return host;
}

async function wait(milliseconds: number) {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, milliseconds)); });
}
const loader = (host: HTMLElement) => host.querySelector('[data-testid="fullscreen-loading"]');
const accepted = { version: "test", accepted_at: "2026-10-23T00:00:00Z" };

test("Business directory, consent, and profile share one visible loader node", async () => {
  const world = requests();
  const host = await mount();
  expect(loader(host)).toBeNull();
  await wait(320);
  const indicator = loader(host);
  expect(indicator).not.toBeNull();
  expect(host.querySelectorAll('[role="status"]').length).toBe(1);
  await act(async () => world.directory.resolve({ spaces: [], closed_spaces: [] }));
  expect(world.calls.some(path => path.endsWith("/consent"))).toBe(true);
  expect(loader(host)).toBe(indicator);
  expect(host.querySelector('[data-layout="overview"]')).toBeNull();
  await act(async () => world.consent.resolve(accepted));
  expect(world.calls).toContain("/mock-profile");
  expect(host.querySelector('[data-testid="profile-startup"]')?.closest("[hidden]")).not.toBeNull();
  expect(loader(host)).toBe(indicator);
  expect(host.querySelectorAll('[role="status"]').length).toBe(1);
  await act(async () => world.profile.resolve());
  expect(host.querySelector('[data-testid="startup-home"]')).not.toBeNull();
  expect(loader(host)).toBeNull();
});

test("short individual stages share the initial delay", async () => {
  const world = requests();
  const host = await mount();
  await wait(170);
  await act(async () => world.directory.resolve({ spaces: [], closed_spaces: [] }));
  expect(loader(host)).toBeNull();
  await wait(160);
  expect(loader(host)).not.toBeNull();
});

test("a fast complete startup never displays an indicator", async () => {
  const world = requests();
  world.directory.resolve({ spaces: [], closed_spaces: [] });
  world.consent.resolve(accepted);
  world.profile.resolve();
  const host = await mount();
  expect(host.querySelector('[data-testid="startup-home"]')).not.toBeNull();
  expect(loader(host)).toBeNull();
  await wait(320);
  expect(loader(host)).toBeNull();
  expect(host.querySelector('[role="status"]')).toBeNull();
});

test("a consent decision immediately replaces a visible loader", async () => {
  const world = requests();
  world.directory.resolve({ spaces: [], closed_spaces: [] });
  const host = await mount();
  await wait(320);
  expect(loader(host)).not.toBeNull();
  await act(async () => world.consent.resolve({ version: "test", accepted_at: null }));
  expect(host.querySelector('[data-testid="business-consent-screen"]')).not.toBeNull();
  expect(loader(host)).toBeNull();
  expect(world.calls).not.toContain("/mock-profile");
});

test("a directory failure immediately replaces a visible loader", async () => {
  const response = deferred<Response>();
  globalThis.fetch = async () => response.promise;
  const host = await mount();
  await wait(320);
  expect(loader(host)).not.toBeNull();
  await act(async () => response.resolve(Response.json({ detail: "unavailable" }, { status: 503 })));
  expect(host.querySelector('[role="alert"]')?.textContent).toBe(spanish.business.lifecycle.errors.discovery);
  expect(loader(host)).toBeNull();
});
