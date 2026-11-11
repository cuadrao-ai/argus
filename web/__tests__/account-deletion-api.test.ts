import { afterEach, beforeEach, describe, expect, test } from "bun:test";

import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  deletionEndsSession,
  endSessionKeepingSurface,
  getAccountDeletionEligibility,
  requestAccountDeletion,
} from "@/lib/account-deletion-api";

type Call = { url: string; body: unknown };

function respond(
  answers: Array<{ status: number; body: unknown } | Error>,
): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    const answer = answers.shift();
    if (!answer) throw new Error("unexpected request");
    if (answer instanceof Error) throw answer;
    return new Response(JSON.stringify(answer.body), {
      status: answer.status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return calls;
}

describe("account deletion outcomes (Lane 6)", () => {
  const originalFetch = globalThis.fetch;
  const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalMockAuth === undefined) {
      delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    } else {
      process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
    }
  });

  test("done and 202 in_progress map to their own states", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    respond([
      { status: 200, body: { status: "done", pending: [] } },
      { status: 202, body: { status: "in_progress", pending: ["apple"] } },
    ]);
    expect(await requestAccountDeletion("en")).toBe("success");
    expect(await requestAccountDeletion("en")).toBe("in_progress");
  });

  test("a 503 after the lock is in progress, not a failure", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    respond([{ status: 503, body: { code: "account_deletion_incomplete" } }]);
    expect(await requestAccountDeletion("en")).toBe("in_progress");
  });

  test("nothing happened: unavailable and network failures throw for a retry", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    respond([{ status: 503, body: { code: "account_deletion_unavailable" } }]);
    await expect(requestAccountDeletion("en")).rejects.toMatchObject({
      status: 503,
      code: "account_deletion_unavailable",
    });
    respond([new TypeError("network down")]);
    await expect(requestAccountDeletion("en")).rejects.toThrow("network down");
  });

  test("with the command off (404) support gets a ticket", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const calls = respond([
      { status: 404, body: { code: "not_found" } },
      { status: 200, body: { success: true } },
    ]);
    expect(await requestAccountDeletion("es-419")).toBe("requested");
    expect(calls[0].url).toEndWith("/account/delete");
    expect(calls[0].body).toEqual({ confirm: true });
    expect(calls[1].url).toEndWith("/feedback");
    expect(calls[1].body).toMatchObject({
      type: "account_deletion_request",
      context: { source: "profile_modal", profile_language: "es-419" },
    });
  });

  test("with the command off and the ticket failing, only email is left", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    respond([
      { status: 404, body: { code: "not_found" } },
      { status: 500, body: { code: "internal_error" } },
    ]);
    expect(await requestAccountDeletion("en")).toBe("unavailable");
  });

  test("deleted or locked ends the session on the result; nothing else does", () => {
    expect(deletionEndsSession("success")).toBe(true);
    expect(deletionEndsSession("in_progress")).toBe(true);
    for (const other of ["requested", "unavailable", "error", "idle", "submitting"]) {
      expect(deletionEndsSession(other)).toBe(false);
    }
  });

  test("the sign-out keeps the surface: the boundary hears first", async () => {
    const order: string[] = [];
    await endSessionKeepingSurface(
      { beginConversion: () => order.push("boundary") },
      async () => {
        order.push("signOut");
        throw new Error("network");
      },
    );
    expect(order).toEqual(["boundary", "signOut"]);
  });

  test("the menu signs out once, on the result; Done only cleans up (#801 N2, note 10)", () => {
    const root = join(import.meta.dir, "..");
    const menu = readFileSync(join(root, "components/sidebar/ProfileMenu.tsx"), "utf-8");
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    expect(menu).toContain(
      "if (deletionEndsSession(outcome)) onLogout({ afterAccountDeletion: true });",
    );
    const close = menu.slice(menu.indexOf("const handleCloseDeleteRequest"));
    expect(close.slice(0, close.indexOf("}, [deleteRequestState, onLogout]);"))).toContain(
      "onLogout({ sessionEnded: true });",
    );
    // Back after a deletion never reaches a bare onLogout() either, which
    // would call logoutFromApi a second time.
    const back = menu.slice(menu.indexOf("if (isDeleteRequestOpen) {"));
    expect(back.slice(0, back.indexOf("closeProfileModal();"))).toContain(
      "onLogout({ sessionEnded: true });",
    );
    expect(back.slice(0, back.indexOf("closeProfileModal();"))).not.toContain("onLogout();");
    expect(chat).toContain(
      "if (options.afterAccountDeletion) return endSessionKeepingSurface(accountBoundary);",
    );
    expect(chat).toContain(
      "signOut: () => (options.sessionEnded ? Promise.resolve(null) : logoutFromApi())",
    );
    // The flow gets the chat's own boundary and the build flag, and Done after
    // deletion is the accountDeleted branch that lands on "/".
    expect(chat).toContain("boundary: accountBoundary,");
    expect(chat).toContain("businessBuild: businessPilotEnabled,");
    expect(chat).toContain("accountDeleted: Boolean(options.sessionEnded),");
  });
});

function deletionCopy(locale: "en" | "es-419"): Record<string, string> {
  const json = JSON.parse(
    readFileSync(join(import.meta.dir, `../public/locales/${locale}/common.json`), "utf-8"),
  );
  return json.settings.profile.request_deletion;
}

describe("the deletion confirmation copy", () => {
  test("never says the account goes now: with the flag off it is a support request (note 9)", () => {
    for (const locale of ["en", "es-419"] as const) {
      const copy = deletionCopy(locale);
      for (const text of [copy.title, copy.body, copy.confirm]) {
        expect(text).not.toMatch(/\bnow\b|\bahora\b|signs you out|cierra tu sesión/i);
      }
    }
    expect(deletionCopy("en").requested).toBe(
      "Request sent. Support will delete your account and follow up by email.",
    );
  });
});

describe("the server's delete rule, read before the alert offers Eliminar", () => {
  const originalFetch = globalThis.fetch;
  const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  beforeEach(() => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  });

  test("an allowed account carries its closed-business notices and nothing else", async () => {
    const notice = { kind: "closed_business", business_id: "b-1", business_name: "Colmado Rosa", purge_at: "2026-11-20T17:45:00Z" };
    const calls = respond([{ status: 200, body: { allowed: true, blockers: [], notices: [notice, { kind: "later" }] } }]);
    expect(await getAccountDeletionEligibility()).toEqual({ allowed: true, blockers: [], notices: [notice] });
    expect(calls[0].url).toEndWith("/account/deletion");
  });

  test("an unnamed Business keeps its blocker and its notice with a null name", async () => {
    const blocker = { kind: "business_owner", business_id: "b-3", business_name: null };
    const notice = { kind: "closed_business", business_id: "b-4", business_name: null, purge_at: "2026-11-20T17:45:00Z" };
    respond([{ status: 200, body: { allowed: false, blockers: [blocker], notices: [notice] } }]);
    expect(await getAccountDeletionEligibility()).toEqual({ allowed: false, blockers: [blocker], notices: [notice] });
  });

  test("an owner is blocked by name, and a reason the web does not know still refuses", async () => {
    respond([{ status: 200, body: { allowed: false, blockers: [{ kind: "business_owner", business_id: "b-2", business_name: "Taller Luna" }, { kind: "something_new" }] } }]);
    expect(await getAccountDeletionEligibility()).toEqual({
      allowed: false,
      blockers: [{ kind: "business_owner", business_id: "b-2", business_name: "Taller Luna" }, { kind: "not_allowed" }],
      notices: [],
    });
  });

  test("a refusal with no reason given is not_allowed, never an open door", async () => {
    respond([{ status: 200, body: { allowed: false, blockers: [] } }]);
    expect(await getAccountDeletionEligibility()).toEqual({ allowed: false, blockers: [{ kind: "not_allowed" }], notices: [] });
    respond([{ status: 200, body: { allowed: true, blockers: [{ kind: "not_allowed" }] } }]);
    expect(await getAccountDeletionEligibility()).toEqual({ allowed: false, blockers: [{ kind: "not_allowed" }], notices: [] });
  });

  test("off here (404) keeps the support-ticket path; any other failure is for a retry", async () => {
    respond([{ status: 404, body: { detail: "not found" } }]);
    expect(await getAccountDeletionEligibility()).toEqual({ off: true });
    respond([{ status: 500, body: { detail: "boom" } }]);
    await expect(getAccountDeletionEligibility()).rejects.toBeDefined();
  });

  test("a check the server could not run (503) is for a retry, not an answer", async () => {
    respond([{ status: 503, body: { code: "account_deletion_unavailable", detail: "unavailable" } }]);
    await expect(getAccountDeletionEligibility()).rejects.toMatchObject({ status: 503, code: "account_deletion_unavailable" });
  });
});
