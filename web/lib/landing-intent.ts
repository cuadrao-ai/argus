import { readReturnPath, returnPathFor } from "./auth-return-path";
import { businessPilotEnabled } from "./private-alpha-flags";
import {
  readSessionStored,
  readStored,
  removeSessionStored,
  writeSessionStored,
  writeStored,
} from "./browser-storage";

/**
 * First-touch campaign capture for ad landings.
 *
 * Semantics:
 * - Persist the first attributed visit as a whole. Later campaign visits
 *   cannot add, replace, or backfill fields, so "which ad brought this
 *   person in" stays one real visit instead of a stitched tuple.
 * - `starter` on the stored attribution object is part of that first visit.
 *   Composer prefill is a separate consume-once session intent written
 *   from this visit's URL, so a later `starter=` can still prefill without
 *   rewriting first-touch attribution.
 * - Campaign fields are trimmed, stripped of control characters, and
 *   length-capped. They keep decoded punctuation and spaces.
 * - `starter` is an exact match on the raw decoded value (`backtest` |
 *   `savings`). No trim, lowercasing, or control-char stripping first.
 *   Duplicate `starter` keys drop the field entirely so /chat and the
 *   login bounce cannot disagree. Anything else is dropped so a link
 *   can never inject free text into the composer or a model request.
 */

export const LANDING_INTENT_STORAGE_KEY = "argus:landing-intent:v1";
export const LANDING_STARTER_STORAGE_KEY = "argus:landing-starter:v1";

export const LANDING_STARTERS = ["backtest", "savings"] as const;
export type LandingStarter = (typeof LANDING_STARTERS)[number];

export const CAMPAIGN_VALUE_FIELDS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "fbclid",
  "ref",
] as const;

export const ATTRIBUTION_FIELDS = [
  ...CAMPAIGN_VALUE_FIELDS,
  "starter",
  "landing_path",
] as const;

export type CampaignValueField = (typeof CAMPAIGN_VALUE_FIELDS)[number];
export type AttributionField = (typeof ATTRIBUTION_FIELDS)[number];

export type LandingIntent = {
  [K in CampaignValueField]?: string;
} & {
  starter?: LandingStarter;
  landing_path?: string;
};

export type AttributionPayload = {
  [K in AttributionField]?: string;
};

const VALUE_MAX_LENGTH = 256;
const PATH_MAX_LENGTH = 200;

const LANDING_STARTER_COPY_KEYS = {
  backtest: "chat.landing_starters.backtest",
  savings: "chat.landing_starters.savings",
} as const;

export const LANDING_STARTER_COPY_FALLBACKS = {
  backtest: "What if I had bought an S&P 500 fund over the last 12 months?",
  savings: "If I set aside $200 every month, what would that add up to in a year?",
} as const;

function stripControls(value: string | null | undefined): string | undefined {
  if (typeof value !== "string") return undefined;
  const cleaned = value.replace(/[\u0000-\u001F\u007F]/g, "").trim();
  return cleaned || undefined;
}

function sanitizeCampaignValue(
  value: string | null | undefined,
  maxLength = VALUE_MAX_LENGTH,
): string | undefined {
  const cleaned = stripControls(value);
  return cleaned ? cleaned.slice(0, maxLength) : undefined;
}

export function sanitizeLandingStarter(
  value: string | null | undefined,
): LandingStarter | undefined {
  return LANDING_STARTERS.find((starter) => starter === value);
}

export function parseLandingStarter(
  search: string | URLSearchParams,
): LandingStarter | undefined {
  const params = toSearchParams(search);
  const values = params.getAll("starter");
  if (values.length !== 1) return undefined;
  return sanitizeLandingStarter(values[0]);
}

export function sanitizeLandingPath(
  value: string | null | undefined,
): string | undefined {
  if (typeof value !== "string") return undefined;
  const cleaned = value.replace(/[\u0000-\u001F\u007F]/g, "").trim();
  if (!cleaned.startsWith("/") || cleaned.startsWith("//") || cleaned.includes("://")) {
    return undefined;
  }
  const path = cleaned.split("?")[0]?.split("#")[0] ?? "";
  if (!path.startsWith("/") || path.startsWith("//") || path.length > PATH_MAX_LENGTH) {
    return undefined;
  }
  return path;
}

type SearchRecord = Record<string, string | string[] | undefined>;

function toSearchParams(
  search: string | URLSearchParams | SearchRecord,
): URLSearchParams {
  if (search instanceof URLSearchParams) return search;
  if (typeof search === "string") {
    return new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  }
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(search)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === "string") params.append(key, item);
      }
    } else if (typeof value === "string") {
      params.append(key, value);
    }
  }
  return params;
}

function campaignValuesFrom(
  read: (field: CampaignValueField) => string | null | undefined,
): Pick<LandingIntent, CampaignValueField> {
  const next: Pick<LandingIntent, CampaignValueField> = {};
  for (const field of CAMPAIGN_VALUE_FIELDS) {
    const value = sanitizeCampaignValue(read(field));
    if (value) next[field] = value;
  }
  return next;
}

function withDefinedFields(intent: LandingIntent): LandingIntent {
  const next: LandingIntent = {};
  for (const field of CAMPAIGN_VALUE_FIELDS) {
    const value = intent[field];
    if (value) next[field] = value;
  }
  if (intent.starter) next.starter = intent.starter;
  if (intent.landing_path) next.landing_path = intent.landing_path;
  return next;
}

export function parseLandingIntent(
  search: string | URLSearchParams,
  landingPath?: string,
): LandingIntent {
  const params = toSearchParams(search);
  const requestedPath = sanitizeLandingPath(landingPath);
  const bouncedFromChat =
    params.get("from_path") === "/chat" &&
    (!requestedPath || requestedPath === "/");
  const starter = parseLandingStarter(params);
  const intent = withDefinedFields({
    ...campaignValuesFrom((field) => params.get(field)),
    starter,
    landing_path: bouncedFromChat ? "/chat" : requestedPath,
  });
  if (hasCampaignAttribution(intent)) return intent;
  return starter ? { starter } : {};
}

export function isEmptyLandingIntent(
  intent: LandingIntent | AttributionPayload | null | undefined,
): boolean {
  if (!intent) return true;
  return ATTRIBUTION_FIELDS.every((field) => !intent[field]);
}

export function mergeFirstTouchLandingIntent(
  existing: LandingIntent | null,
  incoming: LandingIntent,
): LandingIntent {
  if (existing && hasCampaignAttribution(existing)) {
    return withDefinedFields(existing);
  }
  return withDefinedFields(incoming);
}

function sanitizeStoredIntent(raw: Record<string, unknown>): LandingIntent | null {
  const intent = withDefinedFields({
    ...campaignValuesFrom((field) =>
      typeof raw[field] === "string" ? raw[field] : undefined,
    ),
    starter: sanitizeLandingStarter(typeof raw.starter === "string" ? raw.starter : undefined),
    landing_path: sanitizeLandingPath(typeof raw.landing_path === "string" ? raw.landing_path : undefined),
  });
  return isEmptyLandingIntent(intent) ? null : intent;
}

export function readLandingIntent(): LandingIntent | null {
  try {
    const raw = readStored(LANDING_INTENT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    return sanitizeStoredIntent(parsed as Record<string, unknown>);
  } catch {
    return null;
  }
}

const STARTER_CONSUMED_PREFIX = "consumed:";
const STARTER_HANDOFF_PREFIX = "handoff:";

/** Strict Mode remounts the first composer in the same tick. New chat does not. */
export const LANDING_STARTER_RUNTIME_FALLBACK_MS = 2000;

let appliedStarterThisRuntime: LandingStarter | null = null;
let appliedStarterAtMs = 0;
let starterSurfaceEpoch = 0;
let starterComposerUntouched = false;

function readSessionStarterState(): {
  pending: LandingStarter | null;
  consumed: LandingStarter | null;
} {
  const raw = readSessionStored(LANDING_STARTER_STORAGE_KEY);
  if (!raw) return { pending: null, consumed: null };
  if (raw.startsWith(STARTER_CONSUMED_PREFIX)) {
    return {
      pending: null,
      consumed:
        sanitizeLandingStarter(raw.slice(STARTER_CONSUMED_PREFIX.length)) ?? null,
    };
  }
  if (raw.startsWith(STARTER_HANDOFF_PREFIX)) {
    return {
      pending:
        sanitizeLandingStarter(raw.slice(STARTER_HANDOFF_PREFIX.length)) ?? null,
      consumed: null,
    };
  }
  return { pending: sanitizeLandingStarter(raw) ?? null, consumed: null };
}

export function captureLandingIntent(
  search: string | URLSearchParams,
  landingPath?: string,
): LandingIntent | null {
  const incoming = parseLandingIntent(search, landingPath);
  if (incoming.starter) {
    const { consumed } = readSessionStarterState();
    if (consumed !== incoming.starter) {
      writeSessionStored(LANDING_STARTER_STORAGE_KEY, incoming.starter);
    }
  }
  const merged = mergeFirstTouchLandingIntent(readLandingIntent(), incoming);
  if (!hasCampaignAttribution(merged)) return null;
  writeStored(LANDING_INTENT_STORAGE_KEY, JSON.stringify(merged));
  return merged;
}

export function captureLandingIntentFromLocation(): LandingIntent | null {
  if (typeof window === "undefined") return null;
  return captureLandingIntent(window.location.search, window.location.pathname);
}

export function attributionPayload(
  intent: LandingIntent | null = readLandingIntent(),
): AttributionPayload | undefined {
  if (!intent || isEmptyLandingIntent(intent)) return undefined;
  const payload: AttributionPayload = {};
  for (const field of ATTRIBUTION_FIELDS) {
    const value = intent[field];
    if (value) payload[field] = value;
  }
  return isEmptyLandingIntent(payload) ? undefined : payload;
}

export function attributionBody(): { attribution?: AttributionPayload } {
  const attribution = attributionPayload();
  return attribution ? { attribution } : {};
}

export function hasCampaignAttribution(
  intent: LandingIntent | null = readLandingIntent(),
): boolean {
  if (!intent) return false;
  return CAMPAIGN_VALUE_FIELDS.some((field) => Boolean(intent[field]));
}

export function takeLandingStarterPrefill(): LandingStarter | null {
  const { pending, consumed } = readSessionStarterState();
  if (pending) {
    writeSessionStored(
      LANDING_STARTER_STORAGE_KEY,
      `${STARTER_CONSUMED_PREFIX}${pending}`,
    );
    appliedStarterThisRuntime = pending;
    appliedStarterAtMs = Date.now();
    return pending;
  }
  if (!consumed) {
    removeSessionStored(LANDING_STARTER_STORAGE_KEY);
  }
  return null;
}

export function landingStarterAppliedThisRuntime(): LandingStarter | null {
  if (!appliedStarterThisRuntime) return null;
  if (Date.now() - appliedStarterAtMs > LANDING_STARTER_RUNTIME_FALLBACK_MS) {
    appliedStarterThisRuntime = null;
    appliedStarterAtMs = 0;
    return null;
  }
  return appliedStarterThisRuntime;
}

export function landingStarterSurfaceEpoch(): number {
  return starterSurfaceEpoch;
}

export function noteLandingStarterComposerMatch(matchesApplied: boolean): void {
  starterComposerUntouched = matchesApplied;
}

export function resetLandingStarterRuntime(): void {
  appliedStarterThisRuntime = null;
  appliedStarterAtMs = 0;
  starterSurfaceEpoch += 1;
  starterComposerUntouched = false;
  const raw = readSessionStored(LANDING_STARTER_STORAGE_KEY);
  if (!raw?.startsWith(STARTER_HANDOFF_PREFIX)) return;
  const starter = sanitizeLandingStarter(
    raw.slice(STARTER_HANDOFF_PREFIX.length),
  );
  if (starter) {
    writeSessionStored(
      LANDING_STARTER_STORAGE_KEY,
      `${STARTER_CONSUMED_PREFIX}${starter}`,
    );
  }
}

export function prepareLandingStarterAuthHandoff(): void {
  const { pending, consumed } = readSessionStarterState();
  const starter = pending ?? (starterComposerUntouched ? consumed : null);
  if (!starter) return;
  writeSessionStored(
    LANDING_STARTER_STORAGE_KEY,
    `${STARTER_HANDOFF_PREFIX}${starter}`,
  );
}

export function stripLandingStarterFromLocation(): void {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  if (!params.has("starter")) return;
  params.delete("starter");
  const query = params.toString();
  const next = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash ?? ""}`;
  window.history.replaceState(null, "", next);
}

export function landingStarterCopyKey(
  starter: LandingStarter,
): (typeof LANDING_STARTER_COPY_KEYS)[LandingStarter] {
  return LANDING_STARTER_COPY_KEYS[starter];
}

export function pathWithSearch(pathname: string, search: string): string {
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search,
  );
  if (pathname === "/chat") {
    params.delete("auth");
    params.delete("return_to");
  }
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

export function currentChatPath(): string {
  return pathWithSearch(
    "/chat",
    typeof window === "undefined" ? "" : window.location.search,
  );
}

/** The Business shell for an address that named chat: /biz with the conversation and message it carried, nothing else. */
export function businessShellPath(search: URLSearchParams | SearchRecord | string): string {
  const source = toSearchParams(search);
  const kept = new URLSearchParams();
  for (const key of ["conversation", "message"]) {
    const value = source.get(key);
    if (value && /^[A-Za-z0-9_-]{1,128}$/.test(value)) kept.set(key, value);
  }
  const query = kept.toString();
  return query ? `/biz?${query}` : "/biz";
}

/** The signed-in home: the Business workspace on a Business build, else chat with the current query. */
export function signedInHomePath(businessBuild: boolean = businessPilotEnabled): string {
  return businessBuild ? "/biz" : currentChatPath();
}

/** Where to go after signing in: a listed return page, else the signed-in home. */
export function postAuthPath(businessBuild: boolean = businessPilotEnabled): string {
  if (typeof window === "undefined") return signedInHomePath(businessBuild);
  return readReturnPath(window.location.search) ?? signedInHomePath(businessBuild);
}

export function currentAuthLoginPath(): string {
  return authLoginPathFromSearch(
    typeof window === "undefined" ? "" : window.location.search,
    typeof window === "undefined" ? undefined : window.location.pathname,
  );
}

export function authLoginPathFromSearch(
  search: URLSearchParams | SearchRecord | string,
  landingPath?: string,
): string {
  const source = toSearchParams(search);
  const params = new URLSearchParams();
  const campaign = campaignValuesFrom((field) => source.get(field));
  for (const key of CAMPAIGN_VALUE_FIELDS) {
    const value = campaign[key];
    if (value) params.set(key, value);
  }
  const starter = parseLandingStarter(source);
  if (starter) params.set("starter", starter);
  if (sanitizeLandingPath(landingPath) === "/chat") {
    params.set("from_path", "/chat");
  }
  const returnTo = returnPathFor(sanitizeLandingPath(landingPath), source);
  if (returnTo) params.set("return_to", returnTo);
  params.set("auth", "login");
  return `/?${params.toString()}`;
}
