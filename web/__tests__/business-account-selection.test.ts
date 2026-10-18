import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { getChosenGrant, setChosenGrant, synchronizeBusinessAccount, chosenGrantHeader } from "@/lib/business-grant";
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
test("unowned legacy persisted choices cannot become another account's context", () => {
  synchronizeBusinessAccount(null);
  writeStored("argus:business-grant:v1", grant);
  synchronizeBusinessAccount("legacy-reader");
  expect(getChosenGrant()).toBeNull();
});
