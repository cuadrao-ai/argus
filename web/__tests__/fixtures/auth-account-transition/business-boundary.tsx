import assert from "node:assert/strict";
import { afterAll, beforeAll, beforeEach, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createContext, useContext, type ReactNode } from "react";
import { useChatAccountBoundary } from "@/components/chat/useChatAccountBoundary";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";

type Session = { user: { id: string } } | null;
type SessionRead = { data: { session: Session }; error: Error | null };
type UserRead = { data: { user: NonNullable<Session>["user"] | null }; error: Error | null };
type Listener = (event: string, session: Session) => void;
type Directory = { spaces: { role: "owner" }[]; closed_spaces: { role: "owner" }[] };

const listeners = new Set<Listener>();
const checks: ReturnType<typeof Promise.withResolvers<SessionRead>>[] = [];
const directories: { signal: AbortSignal; owner?: string }[] = [];
const requestScopes: (string | null)[] = [];
let sdkSession: Session;
let lifecycleMode: "open" | "off" | "closed" | "empty" | "denied";
let deferDirectory: ReturnType<typeof Promise.withResolvers<Directory>> | undefined;
let deferUser: ReturnType<typeof Promise.withResolvers<UserRead>> | undefined;
let failClient: boolean;
let retirements: number;
let signal: AbortSignal | undefined;
let invalidateChild: (() => void) | undefined;

mock.module("@/lib/supabase-client", () => ({ getSupabaseClient: () => {
  if (failClient) throw new Error("client initialization failed");
  return { auth: {
    onAuthStateChange: (listener: Listener) => {
      listeners.add(listener);
      return { data: { subscription: { unsubscribe: () => listeners.delete(listener) } } };
    },
    getSession: () => {
      const check = Promise.withResolvers<SessionRead>();
      checks.push(check);
      return check.promise;
    },
    getUser: async () => deferUser ? deferUser.promise : { data: { user: sdkSession?.user ?? null }, error: null },
  } };
} }));
mock.module("@/lib/business-api", () => ({ getBusinessDirectory: async (signal: AbortSignal, owner?: string) => {
  directories.push({ signal, owner });
  if (deferDirectory) return deferDirectory.promise;
  if (lifecycleMode === "off") throw { code: "business_unavailable" };
  if (lifecycleMode === "denied") throw { status: 403 };
  return { spaces: lifecycleMode === "open" ? [{ role: "owner" }] : [], closed_spaces: lifecycleMode === "closed" ? [{ role: "owner" }] : [] };
} }));
const TestOwner = createContext<string | null>(null);
mock.module("@/components/business-app/BusinessWorkspace", () => ({
  BusinessContext: createContext(null),
  BusinessWorkspaceProvider: ({ children, userId }: { children: ReactNode; userId: string | null }) => <TestOwner.Provider value={userId}>{children}</TestOwner.Provider>,
}));
mock.module("@/components/business-app/BusinessNamingProvider", () => ({ default: ({ children }: { children: ReactNode }) => children }));
mock.module("@/components/business-app/BusinessLifecycleControls", () => ({ default: () => <p>Closed controls</p> }));
mock.module("@/components/business-app/BusinessLifecycleEntry", () => ({ default: () => null }));
const requests = { synchronizeAccountScope: (userId: string | null) => requestScopes.push(userId) } as unknown as Parameters<typeof useChatAccountBoundary>[1];
mock.module("@/components/chat/ChatInterface", () => ({ default: function Workspace() {
  const owner = useContext(TestOwner);
  const boundary = useChatAccountBoundary(owner, requests, () => { retirements += 1; });
  signal = boundary.admission.current.signal;
  invalidateChild = boundary.invalidate;
  return <input aria-label="Account draft" data-owner={owner} defaultValue="" />;
} }));
mock.module("@/components/chat/ConversationShellGuard", () => ({ default: () => null }));
mock.module("@/components/business-app/ConversationUnavailableNotice", () => ({ default: () => null }));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz?receipt=private" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(() => GlobalRegistrator.unregister());
beforeEach(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  checks.length = 0;
  directories.length = 0;
  requestScopes.length = 0;
  lifecycleMode = "open";
  sdkSession = null;
  failClient = false;
  retirements = 0;
  signal = undefined;
  invalidateChild = undefined;
  deferDirectory = undefined;
  deferUser = undefined;
});

const session = (id: string | null): Session => id ? { user: { id } } : null;
const success = (id: string | null): SessionRead => ({ data: { session: session(id) }, error: null });
async function mount() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { default: i18next } = await import("i18next");
  const { I18nextProvider } = await import("react-i18next");
  const { default: english } = await import("@/public/locales/en/common.json");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", resources: { en: { translation: english } }, interpolation: { escapeValue: false } });
  Object.assign(liveBusinessDataSource, { consent: async (version: string) => ({ version, accepted_at: "2026-10-18T12:00:00.000Z" }) });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const render = (key = "first") => act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessApp key={key} /></I18nextProvider>));
  await render();
  return {
    host, act, render,
    input: () => host.querySelector("input"),
    title: () => host.querySelector('[data-testid="session-recovery-screen"] h1')?.textContent,
    button: () => host.querySelector<HTMLButtonElement>('[data-testid="session-recovery-screen"] button')!,
    focus: () => act(async () => { window.dispatchEvent(new Event("focus")); }),
    resolve: (index: number, id: string | null) => act(async () => checks[index].resolve(success(id))),
    emit: (event: string, id: string | null) => act(async () => {
      sdkSession = session(id);
      for (const listener of listeners) listener(event, sdkSession);
    }),
    unmount: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

test("an unresolved initial null event waits for the actual read and a settled null offers sign-in", async () => {
  const page = await mount();
  try {
    assert.equal(page.input(), null);
    await page.emit("INITIAL_SESSION", null);
    assert.equal(page.title(), undefined);
    await page.resolve(0, null);
    assert.equal(page.title(), "Sign in to continue");
    assert.equal(page.host.querySelector('a[href="/?auth=login"]')?.textContent, "Sign in");
    await page.emit("SIGNED_OUT", null);
    await page.emit("INITIAL_SESSION", "old");
    assert.equal(page.title(), "Sign in to continue");
    assert.equal(page.input(), null, "a late initial event cannot restore a signed-out owner");
  } finally { await page.unmount(); }
});

test("a wake check failure retires the workspace and offers a real retry", async () => {
  const page = await mount();
  try {
    await page.emit("SIGNED_IN", "old");
    const oldInput = page.input()!;
    assert.ok(oldInput, "the signed-in workspace is mounted");
    oldInput.value = "Old private draft";
    oldInput.focus();
    const oldSignal = signal!;
    const oldGeneration = browserAuthGeneration();
    assert.equal(listeners.size, 1, "the parent and its chat boundary share one observer");
    await page.focus();
    assert.equal(checks.length, 2, "waking the Business workspace checks the session");
    assert.equal(page.input(), oldInput);
    assert.equal(document.activeElement, oldInput);
    await page.resolve(1, "old");
    await page.emit("TOKEN_REFRESHED", "old");
    assert.equal(page.input(), oldInput);
    assert.equal(oldInput.value, "Old private draft");
    assert.equal(retirements, 0);
    assert.doesNotThrow(() => requireBrowserAuthGeneration(oldGeneration));
    await page.focus();
    await page.act(async () => checks[2].resolve({ data: { session: null }, error: new Error("offline") }));
    assert.equal(page.input(), null, "an unverifiable session retires the private workspace");
    assert.equal(page.title(), "We couldn’t check your session");
    assert.equal(oldSignal.aborted, true);
    assert.deepEqual(requestScopes, [null]);
    assert.equal(retirements, 1);
    assert.throws(() => requireBrowserAuthGeneration(oldGeneration), /Browser session changed/);
    assert.equal(page.host.querySelector('a[href="/?auth=login"]'), null);
    const retry = page.button();
    assert.equal(retry.textContent, "Retry");
    await page.act(async () => { retry.click(); retry.click(); window.dispatchEvent(new Event("focus")); });
    assert.equal(checks.length, 4, "retry checks once while another click and focus overlap");
    assert.equal(page.button().disabled, true);
    await page.act(async () => checks[3].reject(new Error("again")));
    assert.equal(page.title(), "We couldn’t check your session");
    assert.equal(page.button().disabled, false);
    await page.act(async () => { page.button().click(); });
    await page.resolve(4, "old");
    const freshInput = page.input()!;
    assert.ok(freshInput);
    assert.notEqual(freshInput, oldInput);
    assert.equal(freshInput.value, "");
    assert.equal(retirements, 1);
    assert.deepEqual(directories.map(read => read.owner), ["old", "old"]);
    assert.equal(signal?.aborted, false);
  } finally { await page.unmount(); }
});

test("failed initialization and a thrown read can be retried; only a successful null offers login", async () => {
  failClient = true;
  const page = await mount();
  try {
    assert.equal(page.title(), "We couldn’t check your session");
    assert.equal(checks.length, 0);
    failClient = false;
    await page.act(async () => page.button().click());
    await page.emit("INITIAL_SESSION", null);
    assert.equal(page.button().disabled, true);
    await page.act(async () => checks[0].reject(new Error("offline")));
    assert.equal(page.title(), "We couldn’t check your session");
    await page.act(async () => page.button().click());
    await page.resolve(1, null);
    assert.equal(page.title(), "Sign in to continue");
  } finally { await page.unmount(); }
});

test("the signed-out notification from a failed wake read does not replace its error", async () => {
  const page = await mount();
  try {
    await page.emit("SIGNED_IN", "old");
    await page.focus();
    document.title = "Old private workspace";
    await page.emit("SIGNED_OUT", null);
    assert.equal(page.input(), null);
    assert.equal(document.title, "Cuadrao");
    assert.equal(page.host.querySelector('a[href="/?auth=login"]'), null);
    await page.act(async () => checks[1].resolve({ data: { session: null }, error: new Error("refresh rejected") }));
    assert.equal(page.title(), "We couldn’t check your session");
    assert.equal(page.host.querySelector('a[href="/?auth=login"]'), null);
  } finally { await page.unmount(); }
});

test("a different owner retires the old workspace; only verified admission opens a clean Business home", async () => {
  const page = await mount();
  const replace = window.location.replace;
  const navigations: string[] = [];
  window.location.replace = url => { navigations.push(String(url)); };
  try {
    await page.emit("SIGNED_IN", "old");
    const oldInput = page.input()!;
    oldInput.value = "Old private draft";
    const oldSignal = signal!;
    const invalidateOldChild = invalidateChild!;
    await page.focus();
    deferDirectory = Promise.withResolvers<Directory>();
    await page.emit("SIGNED_IN", "new");
    assert.equal(page.input(), null, "B is not mounted automatically");
    assert.equal(page.title(), "The active account changed");
    assert.equal(page.button().disabled, true);
    assert.equal(oldSignal.aborted, true);
    assert.equal(retirements, 1);
    assert.deepEqual(requestScopes, [null]);
    assert.deepEqual(directories.map(read => read.owner), ["old", "new"]);
    await page.act(async () => invalidateOldChild());
    assert.equal(directories[1].signal.aborted, false);
    assert.equal(checks.length, 2, "a retired child cannot start a new check or cancel admission");
    await page.resolve(0, "old");
    await page.act(async () => checks[1].reject(new Error("stale focus check")));
    assert.equal(page.title(), "The active account changed");
    assert.equal(page.input(), null);
    await page.act(async () => deferDirectory?.resolve({ spaces: [], closed_spaces: [] }));
    deferDirectory = undefined;
    assert.equal(page.button().disabled, false);
    await page.focus();
    await page.resolve(2, "new");
    assert.equal(page.input(), null, "later rechecks never auto-mount B");
    await page.act(async () => page.button().click());
    assert.deepEqual(directories.map(read => read.owner), ["old", "new", "new"]);
    assert.deepEqual(navigations, ["/biz"]);
    assert.equal(page.input(), null);
  } finally {
    window.location.replace = replace;
    await page.unmount();
  }
});

test("denied Business access has a usable retry and cannot admit either account", async () => {
  const page = await mount();
  try {
    await page.emit("SIGNED_IN", "old");
    lifecycleMode = "denied";
    await page.emit("SIGNED_IN", "new");
    assert.equal(page.title(), "We couldn’t check your session");
    assert.equal(page.input(), null);
    await page.act(async () => page.button().click());
    await page.resolve(1, "new");
    assert.equal(page.title(), "We couldn’t check your session");
    assert.equal(page.input(), null);
    lifecycleMode = "open";
    await page.act(async () => page.button().click());
    await page.resolve(2, "new");
    assert.equal(page.title(), "The active account changed");
    assert.equal(page.button().disabled, false);
    assert.equal(page.input(), null);
  } finally { await page.unmount(); }
});

test("a failed destination identity check stays actionable after its signed-out event", async () => {
  const page = await mount();
  try {
    await page.emit("SIGNED_IN", "old");
    deferUser = Promise.withResolvers<UserRead>();
    await page.emit("SIGNED_IN", "new");
    assert.equal(page.button().disabled, true);
    await page.emit("SIGNED_OUT", null);
    assert.equal(page.host.querySelector('a[href="/?auth=login"]'), null);
    await page.act(async () => deferUser?.resolve({ data: { user: null }, error: new Error("could not verify") }));
    assert.equal(page.title(), "We couldn’t check your session");
    assert.equal(page.input(), null);
    assert.deepEqual(directories.map(read => read.owner), ["old"]);
  } finally { await page.unmount(); }
});

test("sign-out supersedes a stale retry and cancels unmount work", async () => {
  const page = await mount();
  await page.emit("SIGNED_IN", "old");
  await page.focus();
  await page.act(async () => checks[1].reject(new Error("offline")));
  await page.act(async () => page.button().click());
  await page.emit("SIGNED_OUT", null);
  await page.resolve(2, "old");
  assert.equal(page.title(), "Sign in to continue");
  assert.equal(page.input(), null);
  await page.focus();
  await page.unmount();
  assert.equal(listeners.size, 0);
  await page.act(async () => checks[3].reject(new Error("unmounted")));
  assert.equal(page.host.childElementCount, 0);
  assert.deepEqual(directories.map(read => read.owner), ["old"]);
});

test("a late old directory response cannot publish after sign-out", async () => {
  const page = await mount();
  try {
    deferDirectory = Promise.withResolvers<Directory>();
    await page.emit("SIGNED_IN", "old");
    assert.equal(page.input(), null);
    await page.emit("SIGNED_OUT", null);
    assert.equal(directories[0].signal.aborted, true);
    await page.act(async () => deferDirectory?.resolve({ spaces: [{ role: "owner" }], closed_spaces: [] }));
    assert.equal(page.input(), null);
    assert.equal(page.title(), "Sign in to continue");
  } finally { await page.unmount(); }
});

test("readiness denial keeps normal Business mounted; closed-only owner never starts workspace bootstrap", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  lifecycleMode = "off";
  const page = await mount();
  try {
    assert.ok(page.input());
    lifecycleMode = "closed";
    await page.render("closed");
    assert.equal(page.input(), null);
    assert.ok(page.host.textContent?.includes("Closed controls"));
  } finally { await page.unmount(); }
});
