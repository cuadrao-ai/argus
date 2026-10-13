import { afterEach, describe, expect, test } from "bun:test";

import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  deletionEndsSession,
  endSessionKeepingSurface,
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

/** Iris's locked copy, item 1 of the handoff's "Copy" section, read from the
 * doc itself so a paraphrase anywhere fails here (Priya #801 B2). */
function lockedItemOne(language: "ES" | "EN"): string {
  const doc = readFileSync(
    join(import.meta.dir, "../../docs/specs/lanes/mvee-five-lane-handoff.md"),
    "utf-8",
  );
  const start = doc.indexOf("**1. Deletion confirmation screen.**");
  const line = doc
    .slice(start, doc.indexOf("**2. Note other members see.**"))
    .split("\n")
    .find((l) => l.startsWith(`- ${language}: "`));
  if (!line) throw new Error(`no ${language} line`);
  return line.slice(`- ${language}: "`.length, -1);
}

function deletionCopy(locale: "en" | "es-419"): Record<string, string> {
  const json = JSON.parse(
    readFileSync(join(import.meta.dir, `../public/locales/${locale}/common.json`), "utf-8"),
  );
  return json.settings.profile.request_deletion;
}

describe("the deletion confirmation copy", () => {
  test("carries Iris's locked block word for word, in both languages", () => {
    const en = lockedItemOne("EN");
    const es = lockedItemOne("ES");
    expect(es).toContain("«Exmiembro»");
    expect(es).toContain("salvo los planes de deuda compartidos");
    expect(en).toContain("Your receipts and notes are deleted.");
    expect(deletionCopy("en").shared_plans).toBe(en);
    expect(deletionCopy("es-419").shared_plans).toBe(es);
    const dialog = readFileSync(
      join(import.meta.dir, "../components/sidebar/ProfileDeleteRequestDialog.tsx"),
      "utf-8",
    );
    expect(dialog).toContain(JSON.stringify(en));
  });

  test("never says the account goes now: with the flag off it is a support request (note 9)", () => {
    for (const locale of ["en", "es-419"] as const) {
      const copy = deletionCopy(locale);
      for (const text of [copy.title, copy.body, copy.shared_plans, copy.confirm]) {
        expect(text).not.toMatch(/\bnow\b|\bahora\b|signs you out|cierra tu sesión/i);
      }
    }
    expect(deletionCopy("en").requested).toBe(
      "Request sent. Support will delete your account and follow up by email.",
    );
  });
});
