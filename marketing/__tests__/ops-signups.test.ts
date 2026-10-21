import { describe, expect, test } from "bun:test";
import {
  planNotice,
  pendingSignups,
  removeSignup,
  sendNotice,
  validateTemplate,
  type ActiveSignup,
  type NoticeTemplate,
  type OpsConfig,
} from "../lib/ops/signups";
import { emailDigest } from "../lib/forms/validation";
import { CONFIG, recordingFetch } from "./forms-support";

const ops: OpsConfig = { ...CONFIG, noticeFrom: "Cuadrao <news@notify.example.test>" };
const row = (email: string, language: "es" | "en" = "es"): ActiveSignup => ({
  email_digest: emailDigest(email),
  email,
  language,
});
const template: NoticeTemplate = {
  id: "availability-1",
  subject: { es: "Ya puedes probar Cuadrao", en: "You can try Cuadrao" },
  text: {
    es: "Hola. Para salir de la lista escribe a hola@cuadrao.ai.",
    en: "Hello. To leave the list write to hola@cuadrao.ai.",
  },
};

describe("removal", () => {
  test("erases an existing legacy address and keeps its suppression digest", async () => {
    const { fetch: doFetch, calls } = recordingFetch(() => Response.json([{ email_digest: "x" }]));
    const result = await removeSignup(ops, " Ana@Example.INVALID ", doFetch, () => new Date("2026-10-08T00:00:00Z"));
    expect(result).toBe("removed");
    expect(calls).toHaveLength(2);
    expect(calls[0].url).toContain(`email_digest=eq.${emailDigest("ana@example.invalid")}&privacy_policy_version=is.null&removed_at=is.null`);
    expect(calls[0].init.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      email: null,
      removed_at: "2026-10-08T00:00:00.000Z",
    });
  });

  test("an absent address stays absent on repeated operator removal", async () => {
    const { fetch: doFetch, calls } = recordingFetch(() => Response.json([]));
    expect(await removeSignup(ops, "ghost@example.invalid", doFetch)).toBe("absent");
    expect(await removeSignup(ops, "ghost@example.invalid", doFetch)).toBe("absent");
    expect(calls.map((call) => call.init.method)).toEqual(["PATCH", "DELETE", "PATCH", "DELETE"]);
    expect(calls[1].url).toContain(`email_digest=eq.${emailDigest("ghost@example.invalid")}&privacy_policy_version=not.is.null`);
  });

  test("personal removal deletes rather than clears a row and a failed delete throws", async () => {
    const { fetch: doFetch, calls } = recordingFetch((call) => Response.json(call.init.method === "DELETE" ? [{ email_digest: "x" }] : []));
    expect(await removeSignup(ops, "ana@example.invalid", doFetch)).toBe("removed");
    expect(calls[1].init.method).toBe("DELETE");
    expect(calls[1].url).not.toContain("removed_at");
    const failed = recordingFetch((call) => call.init.method === "DELETE" ? new Response(null, { status: 503 }) : Response.json([]));
    await expect(removeSignup(ops, "ana@example.invalid", failed.fetch)).rejects.toThrow("HTTP 503");
  });

  test("a database error is raised, not reported as done", async () => {
    const { fetch: doFetch } = recordingFetch(() => new Response("", { status: 500 }));
    await expect(removeSignup(ops, "ana@example.invalid", doFetch)).rejects.toThrow("HTTP 500");
  });
});

describe("notice planning", () => {
  const pending = [row("a@example.invalid"), row("b@example.invalid", "en")];

  test("a full send reaches every pending signup and stamps them", () => {
    expect(planNotice(pending, null)).toEqual({ recipients: pending, stamp: true });
  });

  test("--only reaches only the named pending addresses and never stamps", () => {
    expect(planNotice(pending, [" B@Example.INVALID ", "stranger@example.invalid"])).toEqual({
      recipients: [pending[1]],
      stamp: false,
    });
  });
});

describe("notice template", () => {
  test("accepts a template that tells readers how to leave", () => {
    expect(validateTemplate(template)).toEqual([]);
  });

  test("rejects a notice without the opt-out address or a language", () => {
    const bad = { ...template, text: { es: "Hola", en: "" } };
    expect(validateTemplate(bad)).toEqual([
      "text.es must mention hola@cuadrao.ai so the reader can opt out",
      "text.en is required",
    ]);
  });
});

// A small stand-in for the signup table and the mail provider, so the tests
// exercise claim-then-send as a database and Resend would actually answer.
function backend(options: {
  rows: Record<string, { removed?: boolean; notifiedAt?: string | null; privacyVersion?: string }>;
  claimStatus?: number;
  // The database saves the claim, then the answer is lost.
  claimAnswerLost?: boolean;
  // The database refuses to release a claim (the update that sets notified_at back to null).
  releaseStatus?: number;
  mail?: (attempt: number, key: string) => Response | "throw";
}) {
  const rows = options.rows;
  const events: string[] = [];
  const sentByKey = new Map<string, Response>();
  let mailCalls = 0;
  const responder = (call: { url: string; init: RequestInit }): Response => {
    if (call.init.method === "PATCH") {
      events.push("patch");
      if (options.releaseStatus && JSON.parse(String(call.init.body)).notified_at === null) {
        return new Response("", { status: options.releaseStatus });
      }
      if (options.claimStatus && JSON.parse(String(call.init.body)).notified_at !== null) {
        return new Response("", { status: options.claimStatus });
      }
      const query = new URL(call.url).searchParams;
      const isClaim = JSON.parse(String(call.init.body)).notified_at !== null;
      const digest = query.get("email_digest")?.replace("eq.", "") ?? "";
      const row = rows[digest];
      const wantsUnnotified = query.get("notified_at") === "is.null";
      const claimedValue = query.get("notified_at")?.replace("eq.", "");
      // Honor the request's own filters, as PostgREST does: a request that does not
      // ask for active rows would match a removed one.
      const requiresActive = query.get("removed_at") === "is.null";
      const matches =
        !!row &&
        (!requiresActive || !row.removed) &&
        (query.get("privacy_policy_version") !== "is.null" || !row.privacyVersion) &&
        (!wantsUnnotified || !row.notifiedAt) &&
        (wantsUnnotified || query.get("notified_at") === null || row.notifiedAt === claimedValue);
      if (!matches) return Response.json([]);
      row.notifiedAt = JSON.parse(String(call.init.body)).notified_at;
      if (options.claimAnswerLost && isClaim) throw new DOMException("timed out", "TimeoutError");
      return Response.json([{ email_digest: digest }]);
    }
    events.push("mail");
    mailCalls += 1;
    const key = (call.init.headers as Record<string, string>)["Idempotency-Key"];
    const answer = options.mail ? options.mail(mailCalls, key) : Response.json({ id: "x" });
    if (answer === "throw") throw new DOMException("timed out", "TimeoutError");
    // The provider answers a repeated key with the original result, never a second send.
    if (answer.ok && sentByKey.has(key)) return sentByKey.get(key)!.clone();
    if (answer.ok) sentByKey.set(key, answer.clone());
    return answer;
  };
  const { fetch: doFetch, calls } = recordingFetch(responder);
  return { doFetch, calls, rows, events, mailCalls: () => mailCalls, delivered: () => sentByKey.size };
}

const NOW = () => new Date("2026-10-09T00:00:00Z");
const a = row("a@example.invalid", "en");
const b = row("b@example.invalid");
const c = row("c@example.invalid");
const fresh = (...list: ActiveSignup[]) => Object.fromEntries(list.map((r) => [r.email_digest, { notifiedAt: null }]));

describe("notice sending", () => {
  test("claims a row, then sends it in its language under a per-recipient key", async () => {
    const { doFetch, calls, events, rows } = backend({ rows: fresh(a) });
    const result = await sendNotice(ops, template, planNotice([a], null), doFetch, NOW);
    expect(result).toEqual({ sent: 1, failed: 0, skipped: 0, unknownOutcome: [], releaseFailed: [], claimUncertain: [], stoppedEarly: false });
    expect(events).toEqual(["patch", "mail"]);
    const email = JSON.parse(String(calls[1].init.body));
    expect(email.to).toEqual(["a@example.invalid"]);
    expect(email.subject).toBe("You can try Cuadrao");
    expect(email.reply_to).toBe("hola@cuadrao.ai");
    expect((calls[1].init.headers as Record<string, string>)["Idempotency-Key"]).toBe(`notice-availability-1-${a.email_digest}`);
    expect(rows[a.email_digest].notifiedAt).toBe("2026-10-09T00:00:00.000Z");
  });

  test("an address removed after the list was read is skipped and never mailed", async () => {
    const { doFetch, events } = backend({ rows: { [a.email_digest]: { removed: true }, ...fresh(b) } });
    const result = await sendNotice(ops, template, planNotice([a, b], null), doFetch, NOW);
    expect(result.skipped).toBe(1);
    expect(result.sent).toBe(1);
    expect(events.filter((event) => event === "mail")).toHaveLength(1);
  });

  test("an address already notified is skipped", async () => {
    const { doFetch, mailCalls } = backend({ rows: { [a.email_digest]: { notifiedAt: "2026-10-08T00:00:00.000Z" } } });
    const result = await sendNotice(ops, template, planNotice([a], null), doFetch, NOW);
    expect(result.skipped).toBe(1);
    expect(mailCalls()).toBe(0);
  });

  test("a database that refuses the claim stops the run before anything is sent, naming that row", async () => {
    const { doFetch, mailCalls } = backend({ rows: fresh(a, b, c), claimStatus: 503 });
    const result = await sendNotice(ops, template, planNotice([a, b, c], null), doFetch, NOW);
    expect(result).toEqual({
      sent: 0,
      failed: 0,
      skipped: 0,
      unknownOutcome: [],
      releaseFailed: [],
      claimUncertain: [a.email_digest],
      stoppedEarly: true,
    });
    expect(mailCalls()).toBe(0);
  });

  test("a claim saved but unanswered is named, because that row is claimed and was never mailed", async () => {
    const { doFetch, mailCalls, rows } = backend({ rows: fresh(a, b), claimAnswerLost: true });
    const result = await sendNotice(ops, template, planNotice([a, b], null), doFetch, NOW);
    expect(result.claimUncertain).toEqual([a.email_digest]);
    expect(result.stoppedEarly).toBe(true);
    expect(mailCalls()).toBe(0);
    expect(rows[a.email_digest].notifiedAt).not.toBeNull();
    // b was never reached and stays eligible for a rerun
    expect(rows[b.email_digest].notifiedAt).toBeNull();
  });

  test("a plain provider refusal releases the claim so a rerun can try again", async () => {
    const { doFetch, rows } = backend({ rows: fresh(a), mail: () => new Response("", { status: 422 }) });
    const result = await sendNotice(ops, template, planNotice([a], null), doFetch, NOW);
    expect(result).toMatchObject({ sent: 0, failed: 1, unknownOutcome: [] });
    expect(rows[a.email_digest].notifiedAt).toBeNull();
  });

  test("a refusal whose claim cannot be released stays claimed and is named as refused, not unknown", async () => {
    const { doFetch, rows } = backend({ rows: fresh(a), releaseStatus: 500, mail: () => new Response("", { status: 422 }) });
    const result = await sendNotice(ops, template, planNotice([a], null), doFetch, NOW);
    expect(result).toMatchObject({ sent: 0, failed: 1, unknownOutcome: [], releaseFailed: [a.email_digest], stoppedEarly: false });
    expect(rows[a.email_digest].notifiedAt).not.toBeNull();
  });

  test("the first send with no usable answer stops the run, so an outage cannot claim every row", async () => {
    const { doFetch, rows, mailCalls } = backend({ rows: fresh(a, b, c), mail: () => new Response("", { status: 503 }) });
    const result = await sendNotice(ops, template, planNotice([a, b, c], null), doFetch, NOW);
    expect(result).toMatchObject({ sent: 0, unknownOutcome: [a.email_digest], stoppedEarly: true });
    expect(mailCalls()).toBe(1);
    expect(rows[b.email_digest].notifiedAt).toBeNull();
    expect(rows[c.email_digest].notifiedAt).toBeNull();
  });

  test("a test send also stops at the first unknown result and claims nothing", async () => {
    const { doFetch, rows, mailCalls } = backend({ rows: fresh(a, b), mail: () => new Response("", { status: 503 }) });
    const result = await sendNotice(ops, template, planNotice([a, b], ["a@example.invalid", "b@example.invalid"]), doFetch, NOW);
    expect(result).toMatchObject({ sent: 0, unknownOutcome: [a.email_digest], stoppedEarly: true });
    expect(mailCalls()).toBe(1);
    expect(rows[a.email_digest].notifiedAt).toBeNull();
  });

  test.each([409, 500, 503])("a %d may have been processed, so the row stays claimed and is named", async (status) => {
    const { doFetch, rows } = backend({ rows: fresh(a), mail: () => new Response("", { status }) });
    const result = await sendNotice(ops, template, planNotice([a], null), doFetch, NOW);
    expect(result).toMatchObject({ sent: 0, failed: 0, unknownOutcome: [a.email_digest] });
    expect(rows[a.email_digest].notifiedAt).not.toBeNull();
  });

  test("a lost response is retried once under the same key and delivers exactly one message", async () => {
    const { doFetch, calls, delivered } = backend({
      rows: fresh(a),
      mail: (attempt) => (attempt === 1 ? "throw" : Response.json({ id: "x" })),
    });
    const result = await sendNotice(ops, template, planNotice([a], null), doFetch, NOW);
    expect(result.sent).toBe(1);
    const keys = calls.filter((call) => call.init.method === "POST").map((call) => (call.init.headers as Record<string, string>)["Idempotency-Key"]);
    expect(keys).toHaveLength(2);
    expect(new Set(keys).size).toBe(1);
    expect(delivered()).toBe(1);
  });

  test.each([422, 429])("a %d after a lost first attempt does not prove nothing was sent, so the claim stays", async (status) => {
    const { doFetch, rows } = backend({
      rows: fresh(a),
      mail: (attempt) => (attempt === 1 ? "throw" : new Response("", { status })),
    });
    const result = await sendNotice(ops, template, planNotice([a], null), doFetch, NOW);
    expect(result).toMatchObject({ sent: 0, failed: 0, unknownOutcome: [a.email_digest] });
    expect(rows[a.email_digest].notifiedAt).not.toBeNull();
  });

  test("no answer after the retry leaves the row claimed, named, and not mailed again by a rerun", async () => {
    const database = backend({ rows: fresh(a), mail: () => "throw" });
    const first = await sendNotice(ops, template, planNotice([a], null), database.doFetch, NOW);
    expect(first.unknownOutcome).toEqual([a.email_digest]);
    const callsAfterFirst = database.mailCalls();
    const rerun = await sendNotice(ops, template, planNotice([a], null), database.doFetch, NOW);
    expect(rerun.skipped).toBe(1);
    expect(database.mailCalls()).toBe(callsAfterFirst);
  });

  test("a test send claims nothing and uses its own key", async () => {
    const { doFetch, calls, events } = backend({ rows: fresh(a) });
    const result = await sendNotice(ops, template, planNotice([a], ["a@example.invalid"]), doFetch);
    expect(result.sent).toBe(1);
    expect(events).toEqual(["mail"]);
    expect((calls[0].init.headers as Record<string, string>)["Idempotency-Key"]).toStartWith("notice-test-");
  });
});


describe("personal consent boundary", () => {
  test("legacy discovery excludes double-opt-in rows", async () => {
    const { fetch: doFetch } = recordingFetch((call) => {
      const filter = new URL(call.url).searchParams.get("privacy_policy_version");
      return Response.json(filter === "is.null" ? [a] : [a, b]);
    });
    expect(await pendingSignups(ops, doFetch)).toEqual([a]);
  });
  test("a stale notice plan cannot claim a row upgraded to personal consent", async () => {
    const database = backend({ rows: { [a.email_digest]: { privacyVersion: "2026-10-16" } } });
    const result = await sendNotice(ops, template, planNotice([a], null), database.doFetch, NOW);
    expect(result.skipped).toBe(1);
    expect(database.delivered()).toBe(0);
  });
});
