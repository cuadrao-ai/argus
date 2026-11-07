import { afterAll, beforeAll, beforeEach, expect, mock, spyOn, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { AuthSecurityPort } from "@/lib/auth-security";
import { readStored, writeStored } from "@/lib/browser-storage";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";

const grantKey = "argus:business-grant:v1";
const grantA = "4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b";
const grantB = "5b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b";
type Session = { user: { id: string } } | null;
let session: Session = null;
let notify: (event: string, session: Session) => void;
let revoke: AuthSecurityPort["signOut"];

function emit(event: string, next: Session) {
  session = next;
  notify(event, next);
}

function selectBusiness(userId: string, grantId: string) {
  emit("SIGNED_IN", { user: { id: userId } });
  setChosenGrant(grantId);
}

mock.module("@supabase/ssr", () => ({
  createBrowserClient: () => ({ auth: {
    onAuthStateChange: (listener: typeof notify) => { notify = listener; },
    getSession: async () => ({ data: { session }, error: null }),
    getClaims: async () => ({ data: { claims: { sub: session?.user.id, session_id: "fixture-session" } }, error: null }),
    getUser: async () => ({ data: { user: session?.user ?? null }, error: null }),
    signOut: (options: Parameters<typeof revoke>[0]) => revoke(options),
  } }),
}));

const { getAuthSecurityActions } = await import("@/lib/auth-security");
const { logoutFromApi } = await import("@/lib/argus-api");
let fetchSpy: ReturnType<typeof spyOn<typeof globalThis, "fetch">>;

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  process.env.NEXT_PUBLIC_SUPABASE_URL = "http://localhost";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "fixture";
  getAuthSecurityActions();
  fetchSpy = spyOn(globalThis, "fetch");
});

beforeEach(() => {
  revoke = async ({ scope }) => {
    if (scope !== "others") emit("SIGNED_OUT", null);
    return { error: null };
  };
  fetchSpy.mockClear().mockImplementation(async () => Response.json({ success: true }));
});

afterAll(async () => {
  fetchSpy.mockRestore();
  await GlobalRegistrator.unregister();
});

test("confirmed local sign-out clears a stored Business before the owner is known", async () => {
  writeStored(grantKey, JSON.stringify({ userId: "owner-a", grantId: grantA }));
  emit("INITIAL_SESSION", null);
  expect(readStored(grantKey)).not.toBeNull();

  expect(await getAuthSecurityActions().signOutThisBrowser()).toMatchObject({ revocation: "complete" });
  expect(readStored(grantKey)).toBeNull();
});

test.each(["signOutThisBrowser", "signOutAllSessions"] as const)("%s clears the selected Business on success", async (action) => {
  selectBusiness("owner-a", grantA);

  expect(await getAuthSecurityActions()[action]()).toMatchObject({ revocation: "complete" });
  expect(getChosenGrant()).toBeNull();
  expect(readStored(grantKey)).toBeNull();
});

test("signing out other sessions keeps this browser's selected Business", async () => {
  selectBusiness("owner-a", grantA);

  expect(await getAuthSecurityActions().signOutOtherSessions()).toMatchObject({ revocation: "complete" });
  expect(getChosenGrant()).toBe(grantA);
  expect(readStored(grantKey)).toBe(JSON.stringify({ userId: "owner-a", grantId: grantA }));
  expect(fetchSpy).not.toHaveBeenCalled();
});

test.each(["signOutThisBrowser", "signOutAllSessions"] as const)("%s keeps the selected Business when revocation fails", async (action) => {
  selectBusiness("owner-a", grantA);
  revoke = async () => {
    emit("SIGNED_OUT", null);
    return { error: new Error("Fixture sign-out failed") };
  };

  expect(await getAuthSecurityActions()[action]()).toMatchObject({ revocation: "failed" });
  expect(getChosenGrant()).toBe(grantA);
  expect(readStored(grantKey)).toBe(JSON.stringify({ userId: "owner-a", grantId: grantA }));
  expect(fetchSpy).not.toHaveBeenCalled();
});

test("late cookie cleanup keeps a newer account's Business during an uncertain session", async () => {
  selectBusiness("owner-a", grantA);
  const cookieStarted = Promise.withResolvers<void>();
  const cookieResult = Promise.withResolvers<Response>();
  fetchSpy.mockImplementation(async () => {
    cookieStarted.resolve();
    return cookieResult.promise;
  });
  const signedOut = logoutFromApi();
  await cookieStarted.promise;
  selectBusiness("owner-b", grantB);
  emit("SIGNED_OUT", null);
  cookieResult.resolve(Response.json({ success: true }));

  expect(await signedOut).toEqual({ revocation: "complete", cookieSync: "cleared" });
  expect(getChosenGrant()).toBe(grantB);
  expect(readStored(grantKey)).toBe(JSON.stringify({ userId: "owner-b", grantId: grantB }));
});

test.each(["owner-a", "owner-b"])("pending revocation keeps a newer Business choice made by %s", async (userId) => {
  selectBusiness("owner-a", grantA);
  const revocationStarted = Promise.withResolvers<void>();
  const revocationResult = Promise.withResolvers<{ error: null }>();
  revoke = () => {
    revocationStarted.resolve();
    return revocationResult.promise;
  };
  const signedOut = getAuthSecurityActions().signOutThisBrowser();
  await revocationStarted.promise;
  selectBusiness(userId, grantB);
  emit("SIGNED_OUT", null);
  revocationResult.resolve({ error: null });

  expect(await signedOut).toMatchObject({ revocation: "complete" });
  expect(getChosenGrant()).toBe(grantB);
  expect(readStored(grantKey)).toBe(JSON.stringify({ userId, grantId: grantB }));
});
