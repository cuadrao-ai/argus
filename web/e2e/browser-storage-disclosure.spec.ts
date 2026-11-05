import { expect, test } from "@playwright/test";

import { disclosedCookieConcept } from "../lib/browser-cookies";
import { STORAGE_REGISTRY } from "../lib/browser-storage";
import { installMobileShellFixture } from "./support/mobile-shell-fixture";

/**
 * Observation backstop for the storage chokepoint.
 *
 * The chokepoint and the ESLint ban make an undisclosed key hard to write.
 * This watches what a real browser actually kept during a real journey, so it
 * does not depend on predicting syntax: an aliased handle, a wrapper, a
 * dynamic key, or a dependency writing its own key are all recorded the same
 * way, because Storage.prototype is patched before any page script runs.
 *
 * The property asserted is what the copy actually claims: what your browser
 * *holds*. A library write-test that sets a key and immediately removes it
 * leaves nothing on the device, so it is not disclosable state. Those are
 * proven transient from the removal log rather than assumed from absence, and
 * anything a writer keeps still shows up in what remains.
 *
 * Bounded by the journey below. That bound is why the chokepoint exists too.
 */

const DISCLOSED = new Set<string>(Object.keys(STORAGE_REGISTRY));

type StorageEvent = ["set" | "remove", string];

test("every key a real session keeps is a disclosed key", async ({ page }) => {
  await page.addInitScript(() => {
    const events: StorageEvent[] = [];
    (window as unknown as { __argusStorage: StorageEvent[] }).__argusStorage =
      events;

    const setItem = Storage.prototype.setItem;
    const removeItem = Storage.prototype.removeItem;
    const clear = Storage.prototype.clear;

    Storage.prototype.setItem = function (key: string, value: string) {
      events.push(["set", key]);
      return setItem.call(this, key, value);
    };
    Storage.prototype.removeItem = function (key: string) {
      events.push(["remove", key]);
      return removeItem.call(this, key);
    };
    Storage.prototype.clear = function () {
      for (const key of Object.keys(this)) events.push(["remove", key]);
      return clear.call(this);
    };
  });

  // Surfaces that persist anything: the chat shell, theme boot, language
  // detection, and a return trip so restored preferences are written. The
  // legal pages redirect to the published site, so they are not on this
  // journey. The shell fixture stands in for the session that writes them.
  await installMobileShellFixture(page, { account: "registered" });
  for (const path of ["/chat", "/auth/forgot-password", "/chat"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
  }

  const events = await page.evaluate(
    () =>
      (window as unknown as { __argusStorage: StorageEvent[] }).__argusStorage,
  );
  const remaining = await page.evaluate(() =>
    Object.keys(window.localStorage).concat(Object.keys(window.sessionStorage)),
  );

  // What the browser still holds is what the disclosure has to cover.
  const undisclosed = [...new Set(remaining)].filter(
    (key) => !DISCLOSED.has(key),
  );
  expect(
    undisclosed.sort(),
    `keys kept in browser storage but absent from STORAGE_REGISTRY: ${undisclosed.join(
      ", ",
    )}. Register them and disclose them in the privacy copy.`,
  ).toEqual([]);

  // Anything written but not kept must have been removed on purpose, so
  // "transient" is proven from the log rather than inferred from absence.
  const written = new Set(
    events.filter(([kind]) => kind === "set").map(([, key]) => key),
  );
  const removed = new Set(
    events.filter(([kind]) => kind === "remove").map(([, key]) => key),
  );
  const unaccounted = [...written].filter(
    (key) => !DISCLOSED.has(key) && !remaining.includes(key) && !removed.has(key),
  );
  expect(
    unaccounted.sort(),
    `keys written, undisclosed, and neither kept nor explicitly removed: ${unaccounted.join(
      ", ",
    )}`,
  ).toEqual([]);

  // The instrumentation has to have seen something, or an empty result would
  // read as full coverage.
  expect(written.size).toBeGreaterThan(0);
  expect(remaining.length).toBeGreaterThan(0);
});

/**
 * Cookies the web tier writes never pass through the backend registry: the
 * Supabase browser client writes document.cookie itself, and the server
 * adapter forwards dependency-chosen names. This observes whatever actually
 * landed in the jar, so a dependency-added cookie fails here even though no
 * Argus code named it.
 *
 * Bound worth stating: this journey does not sign in, so Supabase auth cookies
 * are not exercised here. Their naming is pinned by a unit test that derives
 * the name the way the library does, and the server adapter refuses an
 * undisclosed name at the door.
 */
test("every cookie a real session leaves is a disclosed cookie", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const cookies = await context.cookies();
  const undisclosed = cookies
    .map((cookie) => cookie.name)
    .filter((name) => !disclosedCookieConcept(name))
    .sort();

  expect(
    undisclosed,
    `cookies present but not covered by COOKIE_DISCLOSURE_RULES: ${undisclosed.join(
      ", ",
    )}. Add a rule and disclose them in the privacy copy.`,
  ).toEqual([]);
});
