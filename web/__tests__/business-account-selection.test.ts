import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { getChosenGrant, setChosenGrant, synchronizeBusinessAccount, chosenGrantHeader, soleClientGrantId } from "@/lib/business-grant";
import { readStored, writeStored } from "@/lib/browser-storage";
beforeAll(() => GlobalRegistrator.register({ url: "http://localhost" }));
afterAll(() => GlobalRegistrator.unregister());
const grant = "4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b";
test("another account cannot inherit a remembered grant, including after reload", () => {
  synchronizeBusinessAccount("old");
  setChosenGrant(grant);
  expect(chosenGrantHeader()).toEqual({ "X-Business-Grant": grant });
  const saved = readStored("argus:business-grant:v1")!;
  synchronizeBusinessAccount("new");
  expect(getChosenGrant()).toBeNull();
  writeStored("argus:business-grant:v1", saved);
  synchronizeBusinessAccount(null);
  synchronizeBusinessAccount("new");
  expect(chosenGrantHeader()).toEqual({});
  expect(readStored("argus:business-grant:v1")).toBeNull();
});
test("same owner token refresh keeps their choice; logout removes it", () => {
  synchronizeBusinessAccount("old");
  setChosenGrant(grant);
  synchronizeBusinessAccount("old");
  expect(getChosenGrant()).toBe(grant);
  synchronizeBusinessAccount(null);
  expect(getChosenGrant()).toBeNull();
  expect(readStored("argus:business-grant:v1")).toBeNull();
});
test("a sole client grant is the Business to enter, and an owned Business is not", () => {
  expect(soleClientGrantId([{ grant_id: grant, role: "accountant" }])).toBe(grant);
  expect(soleClientGrantId([{ grant_id: grant, role: "owner" }])).toBeNull();
  expect(soleClientGrantId([
    { grant_id: grant, role: "owner" },
    { grant_id: "00000000-0000-4000-8000-000000000002", role: "accountant" },
  ])).toBeNull();
});
test("unowned legacy persisted choices cannot become another account's context", () => {
  synchronizeBusinessAccount(null);
  writeStored("argus:business-grant:v1", grant);
  synchronizeBusinessAccount("legacy-reader");
  expect(getChosenGrant()).toBeNull();
});


test("mock local selection restores with no authenticated owner and never enters API headers", async () => {
  const nodeEnv = process.env.NODE_ENV;
  const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  synchronizeBusinessAccount(null);
  try {
    setChosenGrant("local-business-mock");
    const saved = readStored("argus:business-grant:v1")!;
    expect(JSON.parse(saved).userId).toBeNull();
    // A fresh module models a page reload before any auth listener runs.
    const modulePath = "../lib/business-grant.ts?mock-page-reload";
    const fresh: typeof import("@/lib/business-grant") = await import(modulePath);
    expect(fresh.getChosenGrant()).toBe("local-business-mock");
    expect(fresh.chosenGrantHeader()).toEqual({});
  } finally {
    setChosenGrant(null);
    Object.assign(process.env, { NODE_ENV: nodeEnv, NEXT_PUBLIC_MOCK_AUTH: mockAuth });
  }
});
