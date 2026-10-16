import { businessContactEmail } from "../../components/site-copy";
import { PROVIDER_TIMEOUT_MS, type FormsConfig } from "../forms/config";
import { SIGNUP_TABLE } from "../forms/signup";
import { emailDigest, normalizeEmail } from "../forms/validation";
import type { BusinessLocale } from "../site-routes";

// Legacy operator notices must not reach the personal double-opt-in list.

export type ActiveSignup = {
  email_digest: string;
  email: string;
  language: BusinessLocale;
};

export type NoticeTemplate = {
  id: string;
  subject: Record<BusinessLocale, string>;
  text: Record<BusinessLocale, string>;
};

type OpsConfig = FormsConfig & { noticeFrom: string | null };

const PAGE = 500;

function restHeaders(config: OpsConfig, extra: Record<string, string> = {}): Record<string, string> {
  return {
    apikey: config.supabaseServiceKey ?? "",
    Authorization: `Bearer ${config.supabaseServiceKey}`,
    "Content-Type": "application/json",
    ...extra,
  };
}

function table(config: OpsConfig, query = ""): string {
  return `${config.supabaseUrl}/rest/v1/${SIGNUP_TABLE}${query}`;
}

async function checked(response: Response, action: string): Promise<Response> {
  if (!response.ok) throw new Error(`${action} failed with HTTP ${response.status}`);
  return response;
}

// Active and not yet told: the only rows a notice may reach.
export async function pendingSignups(config: OpsConfig, doFetch: typeof fetch): Promise<ActiveSignup[]> {
  const rows: ActiveSignup[] = [];
  for (let offset = 0; ; offset += PAGE) {
    const query = `?select=email_digest,email,language&removed_at=is.null&notified_at=is.null&privacy_policy_version=is.null&order=created_at.asc,email_digest.asc&limit=${PAGE}&offset=${offset}`;
    const response = await checked(
      await doFetch(table(config, query), { headers: restHeaders(config), signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS) }),
      "reading signups",
    );
    const page = (await response.json()) as ActiveSignup[];
    rows.push(...page);
    if (page.length < PAGE) return rows;
  }
}

export async function signupCounts(config: OpsConfig, doFetch: typeof fetch) {
  const count = async (filter: string): Promise<number> => {
    const response = await checked(
      await doFetch(table(config, `?select=email_digest&${filter}`), {
        headers: restHeaders(config, { Prefer: "count=exact", Range: "0-0" }),
        signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
      }),
      "counting signups",
    );
    return Number(response.headers.get("content-range")?.split("/")[1] ?? 0);
  };
  return {
    active: await count("removed_at=is.null"),
    pending: await count("removed_at=is.null&notified_at=is.null"),
    removed: await count("removed_at=not.is.null"),
  };
}

// Only existing legacy rows retain suppression. Personal consent requires whole-row
// deletion; absent addresses stay absent, including repeated removal requests.
export async function removeSignup(
  config: OpsConfig,
  rawEmail: string,
  doFetch: typeof fetch,
  now: () => Date = () => new Date(),
): Promise<"removed" | "absent"> {
  const digest = emailDigest(normalizeEmail(rawEmail));
  const removedAt = now().toISOString();
  const updated = await checked(
    await doFetch(table(config, `?email_digest=eq.${digest}&privacy_policy_version=is.null&removed_at=is.null`), {
      method: "PATCH",
      headers: restHeaders(config, { Prefer: "return=representation" }),
      body: JSON.stringify({ email: null, removed_at: removedAt }),
      signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
    }),
    "removing the signup",
  );
  const legacyRemoved = ((await updated.json()) as unknown[]).length > 0;
  const deleted = await checked(
    await doFetch(table(config, `?email_digest=eq.${digest}&privacy_policy_version=not.is.null`), {
      method: "DELETE",
      headers: restHeaders(config, { Prefer: "return=representation" }),
      signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
    }),
    "deleting the personal signup",
  );
  const personalRemoved = ((await deleted.json()) as unknown[]).length > 0;
  return legacyRemoved || personalRemoved ? "removed" : "absent";
}

export function validateTemplate(template: NoticeTemplate): string[] {
  const problems: string[] = [];
  if (!template.id?.trim()) problems.push("id is required");
  for (const language of ["es", "en"] as const) {
    if (!template.subject?.[language]?.trim()) problems.push(`subject.${language} is required`);
    const text = template.text?.[language] ?? "";
    if (!text.trim()) problems.push(`text.${language} is required`);
    // Every notice must show how to leave the list.
    else if (!text.includes(businessContactEmail)) {
      problems.push(`text.${language} must mention ${businessContactEmail} so the reader can opt out`);
    }
  }
  return problems;
}

export type NoticePlan = {
  recipients: ActiveSignup[];
  stamp: boolean;
};

// --only restricts to named, approved test addresses. Those sends never stamp
// notified_at, so a test cannot use up a real signup's one notice.
export function planNotice(pending: ActiveSignup[], only: string[] | null): NoticePlan {
  if (!only) return { recipients: pending, stamp: true };
  const wanted = new Set(only.map(normalizeEmail));
  return { recipients: pending.filter((row) => wanted.has(row.email)), stamp: false };
}

export type NoticeResult = {
  sent: number;
  // Sent nothing: the provider answered with a plain refusal. The claim was released
  // unless the row is also in releaseFailed.
  failed: number;
  // Not eligible any more when its turn came (removed or already notified).
  skipped: number;
  // The send's outcome is unknown after a retry. The row stays claimed so no rerun
  // can mail it again; the operator checks the provider by this digest.
  unknownOutcome: string[];
  // The provider refused (nothing was sent) but the claim could not be released: the
  // row stays claimed and unsent, so a rerun skips it until the operator clears it.
  releaseFailed: string[];
  // A claim got no usable answer. That row may be claimed but unsent; the run stopped.
  claimUncertain: string[];
  // The run stopped before sending anything further: a claim got no usable answer, or
  // a send's outcome was unknown (a provider outage would otherwise claim every row).
  stoppedEarly: boolean;
};

// A row is claimed (notified_at set) before its message is sent. The claim only
// succeeds for a row that is still active and not yet notified, so a removal or an
// earlier notice is respected at the moment of sending. A failure to claim sends
// nothing. A plain refusal (4xx other than 409) releases the claim. A lost response is retried once under the
// same idempotency key, which the provider answers without sending twice; if that
// still gives no answer the row stays claimed rather than risk a second message.
export async function sendNotice(
  config: OpsConfig,
  template: NoticeTemplate,
  plan: NoticePlan,
  doFetch: typeof fetch,
  now: () => Date = () => new Date(),
): Promise<NoticeResult> {
  const result: NoticeResult = {
    sent: 0,
    failed: 0,
    skipped: 0,
    unknownOutcome: [],
    releaseFailed: [],
    claimUncertain: [],
    stoppedEarly: false,
  };

  const patch = async (query: string, body: Record<string, unknown>, returning: boolean) =>
    checked(
      await doFetch(table(config, query), {
        method: "PATCH",
        headers: restHeaders(config, { Prefer: returning ? "return=representation" : "return=minimal" }),
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
      }),
      "updating the signup",
    );

  const send = (row: ActiveSignup, key: string) =>
    doFetch(`${config.resendApiUrl}/emails`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.resendApiKey}`,
        "Content-Type": "application/json",
        "Idempotency-Key": key,
      },
      body: JSON.stringify({
        from: config.noticeFrom,
        to: [row.email],
        reply_to: businessContactEmail,
        subject: template.subject[row.language],
        text: template.text[row.language],
      }),
      signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
    });

  for (const row of plan.recipients) {
    const key = `${plan.stamp ? "notice" : "notice-test"}-${template.id}-${row.email_digest}`;
    const claimedAt = now().toISOString();
    const active = `?email_digest=eq.${row.email_digest}&removed_at=is.null&privacy_policy_version=is.null`;

    if (plan.stamp) {
      try {
        const claimed = (await (await patch(`${active}&notified_at=is.null`, { notified_at: claimedAt }, true)).json()) as unknown[];
        if (claimed.length === 0) {
          result.skipped += 1;
          continue;
        }
      } catch {
        // The update may have been saved even though its answer was lost, so this
        // row can be claimed and unsent. Name it and stop; nothing further is sent.
        result.claimUncertain.push(row.email_digest);
        result.stoppedEarly = true;
        break;
      }
    }

    let response: Response | null = null;
    // A request that got no answer may still have been processed, so once any
    // attempt is lost a later refusal proves nothing about the first.
    let lost = false;
    for (let attempt = 0; attempt < 2 && response === null; attempt += 1) {
      try {
        response = await send(row, key);
      } catch {
        lost = true;
        response = null;
      }
    }

    // Only a plain client-side refusal on a request that was never lost proves
    // nothing was sent. A 409 (a request with this key is still in flight), a 5xx
    // or any answer after a lost attempt may have been processed.
    const refused =
      !lost && response !== null && response.status >= 400 && response.status < 500 && response.status !== 409;
    if (response?.ok) {
      result.sent += 1;
    } else if (refused) {
      result.failed += 1;
      if (plan.stamp) {
        try {
          await patch(`${active}&notified_at=eq.${encodeURIComponent(claimedAt)}`, { notified_at: null }, false);
        } catch {
          // Could not release: the row stays claimed, which is the safe direction.
          result.releaseFailed.push(row.email_digest);
        }
      }
    } else {
      // Unknown outcome. Stop, so one bad stretch with the provider cannot claim every
      // remaining row and leave each of them to be checked by hand.
      result.unknownOutcome.push(row.email_digest);
      result.stoppedEarly = true;
      break;
    }
  }
  return result;
}

export type { OpsConfig };
