import assert from "node:assert/strict";
import { afterEach, describe, test } from "bun:test";

import {
  contactPageHref,
  defaultLandingAuthMode,
  parseAccountAccessMode,
  readAccountAccessMode,
} from "../lib/account-access";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("the account access mode the server owns", () => {
  test("only the two server answers are modes; anything else is unavailable", () => {
    assert.equal(parseAccountAccessMode({ access_mode: "open" }), "open");
    assert.equal(parseAccountAccessMode({ access_mode: "invite_only" }), "invite_only");
    assert.equal(parseAccountAccessMode({ access_mode: "closed" }), "unavailable");
    assert.equal(parseAccountAccessMode({}), "unavailable");
    assert.equal(parseAccountAccessMode(null), "unavailable");
  });

  test("a bare visit opens on login unless the server says access is open", () => {
    assert.equal(defaultLandingAuthMode("open"), "intro");
    assert.equal(defaultLandingAuthMode("invite_only"), "login");
    assert.equal(defaultLandingAuthMode("unavailable"), "login");
  });

  test("Solicitar acceso goes to the contact page in the shown language", () => {
    assert.equal(contactPageHref("es-419"), "https://cuadrao.ai/contacto");
    assert.equal(contactPageHref(undefined), "https://cuadrao.ai/contacto");
    assert.equal(contactPageHref("en"), "https://cuadrao.ai/en/contact");
    assert.equal(contactPageHref("en-US"), "https://cuadrao.ai/en/contact");
  });

  test("the read asks the public route with no session and takes its answer", async () => {
    const requests: string[] = [];
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      requests.push(String(input));
      return Response.json({ access_mode: "invite_only" });
    }) as typeof fetch;

    assert.equal(await readAccountAccessMode(), "invite_only");
    assert.deepEqual(requests, ["http://127.0.0.1:8000/api/v1/auth/access-mode"]);
  });

  test("a failed read is unavailable, never a mode the web made up", async () => {
    globalThis.fetch = (async () => Response.json({ code: "internal_error" }, { status: 500 })) as typeof fetch;
    assert.equal(await readAccountAccessMode(), "unavailable");

    globalThis.fetch = (async () => { throw new TypeError("network down"); }) as typeof fetch;
    assert.equal(await readAccountAccessMode(), "unavailable");
  });
});
