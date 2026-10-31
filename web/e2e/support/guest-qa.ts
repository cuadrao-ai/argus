import { createHash, createHmac, randomBytes, randomUUID } from "node:crypto";
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { chmodSync, mkdirSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import {
  expect,
  type APIRequestContext,
  type BrowserContext,
  type Page,
  type Request,
} from "@playwright/test";
import { guestQaEndpointConfig } from "./guest-qa-endpoints";

export const REPOSITORY_ROOT = path.resolve(__dirname, "../../..");
const QA_ENDPOINTS = guestQaEndpointConfig();
export const LOCAL_APP_ORIGIN = QA_ENDPOINTS.appOrigin;
export const LOCAL_APP_PORT = QA_ENDPOINTS.appPort;
export const LOCAL_API_ORIGIN = QA_ENDPOINTS.apiOrigin;
export const LOCAL_API_PORT = QA_ENDPOINTS.apiPort;
export const LOCAL_API_BASE = QA_ENDPOINTS.apiBase;
const LOCAL_DB_CONTAINER = QA_ENDPOINTS.databaseContainer;
const UUID_PATTERN =
  /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi;
const JWT_PATTERN = /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g;
const EMAIL_PATTERN = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
const STRICT_UTC_TIMESTAMP_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(?:Z|\+00(?::?00)?)$/;

function canonicalStrictUtcTimestamp(
  value: string | null | undefined,
): string | null {
  if (typeof value !== "string") return null;
  const match = STRICT_UTC_TIMESTAMP_PATTERN.exec(value);
  if (!match) return null;

  const [, yearText, monthText, dayText, hourText, minuteText, secondText] =
    match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) {
    return null;
  }

  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [
    31,
    leapYear ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ][month - 1];
  if (day < 1 || day > daysInMonth) return null;

  const microseconds = (match[7] ?? "").padEnd(6, "0");
  return `${yearText}-${monthText}-${dayText}T${hourText}:${minuteText}:${secondText}.${microseconds}Z`;
}

export function strictUtcTimestampsEqual(
  left: string | null | undefined,
  right: string | null | undefined,
): boolean {
  const canonicalLeft = canonicalStrictUtcTimestamp(left);
  const canonicalRight = canonicalStrictUtcTimestamp(right);
  return canonicalLeft !== null && canonicalLeft === canonicalRight;
}

export const GUEST_ACCEPTANCE_CHECKS = [
  { number: 1, title: "Public entry opens chat without login" },
  { number: 2, title: "English and Spanish guest chrome is complete" },
  { number: 3, title: "Starter chip uses ordinary chat" },
  { number: 4, title: "Clarification and confirmation preserve the idea" },
  { number: 5, title: "One simulation completes in the ordinary result card" },
  { number: 6, title: "Chart switching creates zero writes" },
  { number: 7, title: "UI API and Postgres usage agree" },
  { number: 8, title: "Reload restores the exact conversation and result" },
  {
    number: 9,
    title: "Recents restores the temporary conversation and expiry",
  },
  { number: 10, title: "Omnisearch is owner scoped and honest" },
  { number: 11, title: "Third simulation converts before admission" },
  { number: 12, title: "Add decision preserves typed action identity" },
  { number: 13, title: "New chat choices match account-access mode" },
  { number: 14, title: "Canceling authentication loses nothing" },
  {
    number: 15,
    title: "New account conversion preserves UUID and resumes once",
  },
  { number: 16, title: "Existing account claim is atomic and lossless" },
  { number: 17, title: "Guest feedback is private and allowance neutral" },
  { number: 18, title: "Interrupted turn charges nothing and recovers" },
  { number: 19, title: "Expiry and cleanup are bounded and safe" },
  { number: 20, title: "Global browser ownership and secret safety hold" },
] as const;

export type GuestCheckNumber =
  (typeof GUEST_ACCEPTANCE_CHECKS)[number]["number"];

export type PersistedMessageItem = {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  metadata?: Record<string, unknown>;
};

export type ConfirmationDateRange = {
  start: string;
  end: string;
};

export type ConfirmationFacts = {
  messageId: string;
  confirmationId: string;
  assetUniverse: string[];
  benchmark: string;
  requestedDateRange: ConfirmationDateRange;
  effectiveDateRange: ConfirmationDateRange;
};

export type ConfirmationContinuityChecks = {
  updateMessagePersisted: boolean;
  assetUniverseExactlyMsft: boolean;
  benchmarkExactlySpy: boolean;
  requestedDateRangeUnchanged: boolean;
  effectiveDateRangeUnchanged: boolean;
};

export type ResultFacts = {
  messageId: string;
  runId: string;
  evidenceId: string;
};

export type ResultTruthFingerprint = {
  rows: number;
  fingerprint: string;
};

export const CONFIRMATION_CONTINUITY_ASSERTION_MESSAGES = {
  updateMessagePersisted:
    "The exact Check 4 update message was not durably persisted as a user message",
  assetUniverseExactlyMsft:
    'The refined confirmation asset universe must be exactly ["MSFT"]',
  benchmarkExactlySpy:
    "The refined confirmation typed benchmark must remain exactly SPY",
  requestedDateRangeUnchanged:
    "The refined confirmation requested date range must match the initial request",
  effectiveDateRangeUnchanged:
    "The refined confirmation effective canonical date range must remain unchanged",
} satisfies Record<keyof ConfirmationContinuityChecks, string>;

export type BrowserSafetyPhase = "product" | "fault_injection" | "teardown";

export type BrowserSafetyContext = {
  check: GuestCheckNumber | null;
  phase: BrowserSafetyPhase;
};

export type BrowserSafetyDetail = {
  event: "console_error" | "page_error" | "failed_request";
  component: "browser_console" | "browser_page" | "network";
  endpoint: string | null;
  status: number | null;
  category: string;
  check: GuestCheckNumber | null;
  phase: BrowserSafetyPhase;
};

type SafeConfirmationEvidence = {
  message_label: string;
  confirmation_label: string;
  asset_universe: string[];
  benchmark: string;
  requested_date_range: ConfirmationDateRange;
  effective_date_range: ConfirmationDateRange;
};

export type GuestMe = {
  account_kind: "guest" | "registered";
  public_account_access_enabled: boolean;
  user: {
    id: string;
    email: string | null;
    language: "en" | "es-419";
  };
  guest: {
    expires_at: string;
    conversation_id: string | null;
    simulation_limit: number;
    feedback_limit: number;
  } | null;
};

export type UsageWindow = {
  used: number;
  limit: number;
  remaining: number;
  period_end: string;
};

export type GuestUsage = {
  allowances: {
    compute: {
      hour: null;
      day: null;
      guest_session: null;
      available_now: true;
      limiting_window: null;
    };
    grounding: {
      hour: null;
      day: UsageWindow;
      guest_session: null;
      available_now: boolean;
      limiting_window: "day";
    };
    execution: {
      hour: null;
      day: UsageWindow;
      guest_session: UsageWindow;
      available_now: boolean;
      limiting_window: "day" | "guest_session";
    };
  };
};

export type OwnerSnapshot = {
  conversations: number;
  messages: number;
  user_messages: number;
  assistant_messages: number;
  jobs: number;
  succeeded_jobs: number;
  runs: number;
  completed_runs: number;
  ideas: number;
  idea_versions: number;
  evidence: number;
  decisions: number;
  feedback: number;
  chat_units: number;
  simulation_units: number;
  feedback_units: number;
  route_receipts: number;
  cost_rows: number;
  provider_cost_usd: number;
  provider_latency_ms: number;
  expires_at: string | null;
};

export type ConversationGraph = {
  conversation: string[];
  messages: string[];
  strategies: string[];
  jobs: string[];
  runs: string[];
  ideas: string[];
  idea_versions: string[];
  evidence: string[];
  decisions: string[];
  context_packets: string[];
  run_context_packets: string[];
  checkpoints: string[];
  checkpoint_blobs: string[];
  checkpoint_writes: string[];
};

export type CleanupRetentionState = {
  feedback_rows: number;
  usage_rows: number;
  retained_route_rows: number;
  attributed_route_rows: number;
  retained_cost_rows: number;
  attributed_cost_rows: number;
  retained_cost_route_links: number;
};

export type ZeroStateSnapshot = {
  auth_users: number;
  profiles: number;
  disposable_allowlist_rows: number;
  queued_jobs: number;
  running_jobs: number;
  usage_counters: number;
  product_rows: number;
};

export type SafeEvidence = {
  candidate_sha: string;
  served_sha: string;
  frontend_mode: "production";
  status: "passed" | "failed";
  completed_checks: number[];
  failure_check: number | null;
  flags_restored_false: boolean;
  fresh_context_verified: boolean;
  owner_labels: string[];
  conversation_labels: string[];
  artifact_labels: string[];
  check4_initial_confirmation: SafeConfirmationEvidence | null;
  check4_refined_confirmation: SafeConfirmationEvidence | null;
  simulation_usage_matches: boolean;
  distinct_uuid_conversion: boolean;
  new_account_resume_count: number;
  existing_claim_owner_changed: boolean;
  existing_claim_duplicate_count: number;
  existing_claim_resume_count: number;
  feedback_rows_added: number;
  feedback_email_present: boolean;
  feedback_transcript_present: boolean;
  interrupted_usage_delta: number;
  cleanup_deleted_count: number;
  cleanup_permanent_control_preserved: boolean;
  cleanup_complete_graph_rows_before: number;
  cleanup_complete_graph_rows_after: number;
  cleanup_feedback_deleted: boolean;
  cleanup_usage_deleted: boolean;
  cleanup_route_retained: boolean;
  cleanup_cost_retained: boolean;
  cross_owner_result_count: number;
  console_error_count: number;
  page_error_count: number;
  failed_request_count: number;
  browser_safety_details: BrowserSafetyDetail[];
  teardown_console_error_count: number;
  teardown_page_error_count: number;
  teardown_failed_request_count: number;
  teardown_hosted_write_count: number;
  teardown_credential_exposure_count: number;
  hosted_write_count: number;
  server_product_analytics_disabled: boolean;
  credential_exposure_count: number;
  provider_cost_usd: number;
  provider_latency_ms: number;
  normalized_mutation_counts: Record<string, number>;
  teardown_clean: boolean;
};

function recordOrEmpty(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function rekeyGuestQaConfirmationMetadata(
  metadata: Record<string, unknown>,
  nextConfirmationId: string,
): Record<string, unknown> {
  if (!nextConfirmationId.trim()) {
    throw new Error("Guest QA confirmation identity is required");
  }
  const sourceCard = recordOrEmpty(metadata.confirmation_card);
  const sourcePayload = recordOrEmpty(metadata.confirmation_payload);
  const sourceConfirmationId = sourceCard.confirmation_id;
  if (
    typeof sourceConfirmationId !== "string" ||
    !sourceConfirmationId.trim()
  ) {
    throw new Error("Guest QA confirmation identity mismatch");
  }
  const sourceActions = Array.isArray(sourceCard.actions)
    ? sourceCard.actions
    : [];
  const sourceRunActions = sourceActions
    .map(recordOrEmpty)
    .filter((action) => action.type === "run_backtest");
  if (sourceRunActions.length !== 1) {
    throw new Error("Guest QA confirmation must contain one typed run action");
  }
  const sourceRunPayload = recordOrEmpty(sourceRunActions[0]?.payload);
  const activeReference = recordOrEmpty(metadata.active_confirmation_reference);
  const activeReferenceMetadata = recordOrEmpty(activeReference.metadata);
  const artifactReferences = Array.isArray(metadata.artifact_references)
    ? metadata.artifact_references.map(recordOrEmpty)
    : [];
  const payloadConfirmationId = sourcePayload.confirmation_id;
  const payloadArtifactId = sourcePayload.artifact_id;
  const runArtifactId = sourceRunPayload.artifact_id;
  if (
    (payloadConfirmationId !== undefined &&
      payloadConfirmationId !== sourceConfirmationId) ||
    (payloadArtifactId !== undefined &&
      payloadArtifactId !== sourceConfirmationId) ||
    sourceRunPayload.confirmation_id !== sourceConfirmationId ||
    (runArtifactId !== undefined && runArtifactId !== sourceConfirmationId) ||
    activeReference.artifact_id !== sourceConfirmationId ||
    activeReferenceMetadata.confirmation_id !== sourceConfirmationId ||
    !artifactReferences.some(
      (reference) => reference.artifact_id === sourceConfirmationId,
    )
  ) {
    throw new Error("Guest QA confirmation identity mismatch");
  }
  const sourceValidation = recordOrEmpty(sourcePayload.validation);
  if (
    sourceValidation.executable !== true ||
    sourceCard.status !== "ready_to_run"
  ) {
    throw new Error("Guest QA source confirmation is not executable");
  }
  const rekeyExactIdentity = (value: unknown): unknown => {
    if (value === sourceConfirmationId) return nextConfirmationId;
    if (Array.isArray(value)) return value.map(rekeyExactIdentity);
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([key, item]) => [
          key,
          rekeyExactIdentity(item),
        ]),
      );
    }
    return value;
  };
  const clone = rekeyExactIdentity(structuredClone(metadata)) as Record<
    string,
    unknown
  >;
  const card = recordOrEmpty(clone.confirmation_card);
  const actions = Array.isArray(card.actions) ? card.actions : [];
  card.confirmation_state = "active";
  card.actions = actions.map((value) => {
    const action = recordOrEmpty(value);
    if (action.type !== "run_backtest") return action;
    const payload = recordOrEmpty(action.payload);
    payload.idempotency_key = nextConfirmationId;
    action.payload = payload;
    return action;
  });
  clone.confirmation_card = card;
  return clone;
}

function requiredDateRange(
  value: unknown,
  field: string,
): ConfirmationDateRange {
  const record = recordOrEmpty(value);
  if (
    typeof record.start !== "string" ||
    record.start === "" ||
    typeof record.end !== "string" ||
    record.end === ""
  ) {
    throw new Error(`Canonical confirmation is missing typed ${field}`);
  }
  return { start: record.start, end: record.end };
}

export function latestConfirmationFacts(
  items: PersistedMessageItem[],
): ConfirmationFacts {
  for (const item of [...items].reverse()) {
    const metadata = recordOrEmpty(item.metadata);
    const payload = recordOrEmpty(metadata.confirmation_payload);
    const strategy = recordOrEmpty(payload.strategy);
    if (Object.keys(strategy).length === 0) continue;
    const launch = recordOrEmpty(payload.launch_payload);
    const card = recordOrEmpty(metadata.confirmation_card);
    const confirmationId = card.confirmation_id;
    if (typeof confirmationId !== "string" || confirmationId === "") {
      throw new Error(
        "Canonical confirmation is missing a typed confirmation id",
      );
    }
    const benchmark = launch.benchmark_symbol;
    if (typeof benchmark !== "string" || benchmark === "") {
      throw new Error("Canonical confirmation is missing a typed benchmark");
    }
    const assetUniverse = Array.isArray(strategy.asset_universe)
      ? strategy.asset_universe.filter(
          (value): value is string => typeof value === "string",
        )
      : [];
    return {
      messageId: item.id,
      confirmationId,
      assetUniverse,
      benchmark,
      requestedDateRange: requiredDateRange(
        launch.requested_date_range,
        "requested date range",
      ),
      effectiveDateRange: requiredDateRange(
        strategy.date_range,
        "effective canonical date range",
      ),
    };
  }
  throw new Error("A canonical confirmation artifact was not persisted");
}

export function distinctConfirmationFacts(
  items: PersistedMessageItem[],
  initial: Pick<ConfirmationFacts, "messageId" | "confirmationId">,
): ConfirmationFacts | null {
  const latest = latestConfirmationFacts(items);
  if (
    latest.messageId === initial.messageId ||
    latest.confirmationId === initial.confirmationId
  ) {
    return null;
  }
  return latest;
}

function sameDateRange(
  left: ConfirmationDateRange,
  right: ConfirmationDateRange,
): boolean {
  return left.start === right.start && left.end === right.end;
}

export function confirmationContinuityChecks(
  initial: ConfirmationFacts,
  refined: ConfirmationFacts,
  items: PersistedMessageItem[],
  updateMessage: string,
): ConfirmationContinuityChecks {
  return {
    updateMessagePersisted: items.some(
      (item) => item.role === "user" && item.content === updateMessage,
    ),
    assetUniverseExactlyMsft:
      refined.assetUniverse.length === 1 && refined.assetUniverse[0] === "MSFT",
    benchmarkExactlySpy: refined.benchmark === "SPY",
    requestedDateRangeUnchanged: sameDateRange(
      refined.requestedDateRange,
      initial.requestedDateRange,
    ),
    effectiveDateRangeUnchanged: sameDateRange(
      refined.effectiveDateRange,
      initial.effectiveDateRange,
    ),
  };
}

export function latestResultFacts(items: PersistedMessageItem[]): ResultFacts {
  for (const item of [...items].reverse()) {
    const metadata = recordOrEmpty(item.metadata);
    if (!Object.hasOwn(metadata, "result_card")) continue;
    const resultCard = recordOrEmpty(metadata.result_card);
    const runId = metadata.result_run_id;
    const evidenceId =
      resultCard.evidenceArtifactId ?? resultCard.evidence_artifact_id;
    if (
      typeof runId !== "string" ||
      runId === "" ||
      typeof evidenceId !== "string" ||
      evidenceId === ""
    ) {
      throw new Error("Canonical result is missing typed result identities");
    }
    return {
      messageId: item.id,
      runId,
      evidenceId,
    };
  }
  throw new Error("A canonical typed result artifact was not persisted");
}

export function binaryEvidenceDiffers(
  before: Uint8Array,
  after: Uint8Array,
): boolean {
  if (before.length !== after.length) return true;
  return before.some((value, index) => value !== after[index]);
}

export function resultTruthStayedStable(
  before: ResultTruthFingerprint,
  after: ResultTruthFingerprint,
): boolean {
  return (
    before.rows > 0 &&
    before.rows === after.rows &&
    before.fingerprint !== "" &&
    before.fingerprint === after.fingerprint
  );
}

type DisposableIdentity = {
  userId: string;
  email: string;
  password: string;
};

function requireUuid(value: string, label: string): string {
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value,
    )
  ) {
    throw new Error(`${label} is not a UUID`);
  }
  return value;
}

function requireCandidateSha(): string {
  const candidate = process.env.ARGUS_CANDIDATE_SHA?.trim() ?? "";
  if (!/^[0-9a-f]{40}$/.test(candidate)) {
    throw new Error("ARGUS_CANDIDATE_SHA must be an exact 40-character SHA");
  }
  return candidate;
}

function localUrl(value: string | undefined, label: string): URL {
  if (!value) throw new Error(`${label} is required`);
  const parsed = new URL(value);
  if (
    !["http:", "postgresql:", "postgres:"].includes(parsed.protocol) ||
    !["localhost", "127.0.0.1"].includes(parsed.hostname)
  ) {
    throw new Error(`${label} must target loopback`);
  }
  return parsed;
}

export function assertExactLocalCandidate(
  options: { allowMockBrowserAuth?: boolean } = {},
): void {
  if (process.env.ARGUS_QA_APPROVED_SUPABASE_REF) {
    throw new Error(
      "Hosted Supabase approval is forbidden for guest browser QA",
    );
  }
  const candidate = requireCandidateSha();
  const head = execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: REPOSITORY_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();
  const root = execFileSync("git", ["rev-parse", "--show-toplevel"], {
    cwd: REPOSITORY_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();
  const status = execFileSync("git", ["status", "--porcelain"], {
    cwd: REPOSITORY_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();
  if (root !== REPOSITORY_ROOT) throw new Error("Wrong guest QA worktree");
  if (head !== candidate) throw new Error("Candidate SHA does not match HEAD");
  if (status && process.env.ARGUS_GUEST_QA_ALLOW_TEST_DIFF !== "true") {
    throw new Error("Guest QA worktree must be clean");
  }

  localUrl(process.env.NEXT_PUBLIC_SUPABASE_URL, "NEXT_PUBLIC_SUPABASE_URL");
  localUrl(process.env.SUPABASE_PROJECT_URL, "SUPABASE_PROJECT_URL");
  localUrl(process.env.DATABASE_URL, "DATABASE_URL");
  const app = localUrl(
    process.env.PLAYWRIGHT_BASE_URL ?? LOCAL_APP_ORIGIN,
    "PLAYWRIGHT_BASE_URL",
  );
  const api = localUrl(
    process.env.NEXT_PUBLIC_ARGUS_API_URL ?? LOCAL_API_BASE,
    "NEXT_PUBLIC_ARGUS_API_URL",
  );
  if (app.origin !== LOCAL_APP_ORIGIN) {
    throw new Error(`Guest QA app origin must be ${LOCAL_APP_ORIGIN}`);
  }
  if (`${api.origin}${api.pathname.replace(/\/$/, "")}` !== LOCAL_API_BASE) {
    throw new Error(`Guest QA API must be ${LOCAL_API_BASE}`);
  }
  if (options.allowMockBrowserAuth) {
    if (process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") {
      throw new Error("Guest-entry fixtures require mock browser Auth");
    }
  } else if (process.env.NEXT_PUBLIC_MOCK_AUTH !== "false") {
    throw new Error("Guest QA requires real browser Auth");
  }
  if (process.env.CUADRAO_MOCK_AUTH !== "false") {
    throw new Error("Guest QA requires real backend Auth");
  }
  if (process.env.CUADRAO_GUEST_ACCESS_ENABLED !== "true") {
    throw new Error("Guest QA requires the process-only server guest flag");
  }
  if (process.env.NEXT_PUBLIC_GUEST_ACCESS_ENABLED !== "true") {
    throw new Error("Guest QA requires the process-only frontend guest flag");
  }
  for (const key of [
    "POSTHOG_PROJECT_TOKEN",
    "POSTHOG_REGION",
    "POSTHOG_HOST",
  ]) {
    if (process.env[key]?.trim()) {
      throw new Error("Guest QA requires server product analytics disabled");
    }
  }
}

function psqlJson<T>(sql: string): T {
  try {
    const output = execFileSync(
      "docker",
      [
        "exec",
        "-i",
        LOCAL_DB_CONTAINER,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-q",
        "-v",
        "ON_ERROR_STOP=1",
        "-A",
        "-t",
        "-c",
        sql,
      ],
      {
        cwd: REPOSITORY_ROOT,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      },
    ).trim();
    return JSON.parse(output) as T;
  } catch {
    throw new Error("Local guest QA database assertion failed");
  }
}

export function zeroStateSnapshot(): ZeroStateSnapshot {
  return psqlJson<ZeroStateSnapshot>(`
    select json_build_object(
      'auth_users', (select count(*) from auth.users),
      'profiles', (select count(*) from public.profiles),
      'disposable_allowlist_rows', (
        select count(*)
        from public.private_alpha_allowlist
        where email like 'guest-qa-%@example.test'
           or email like 'guest-link-%@example.test'
      ),
      'queued_jobs', (select count(*) from public.backtest_jobs where status = 'queued'),
      'running_jobs', (select count(*) from public.backtest_jobs where status = 'running'),
      'usage_counters', (select count(*) from public.usage_counters),
      'product_rows', (
        (select count(*) from public.guest_workspaces) +
        (select count(*) from public.guest_workspace_handoffs) +
        (select count(*) from public.conversations) +
        (select count(*) from public.messages) +
        (select count(*) from public.strategies) +
        (select count(*) from public.collections) +
        (select count(*) from public.collection_strategies) +
        (select count(*) from public.backtest_jobs) +
        (select count(*) from public.backtest_runs) +
        (select count(*) from public.ideas) +
        (select count(*) from public.idea_versions) +
        (select count(*) from public.evidence_artifacts) +
        (select count(*) from public.decision_notes) +
        (select count(*) from public.feedback) +
        (select count(*) from public.context_packets) +
        (select count(*) from public.run_context_packets) +
        (select count(*) from public.route_receipts) +
        (select count(*) from public.cost_ledger_entries) +
        (select count(*) from public.checkpoints) +
        (select count(*) from public.checkpoint_writes) +
        (select count(*) from public.checkpoint_blobs)
      )
    )::text
  `);
}

export function assertZeroState(): ZeroStateSnapshot {
  const state = zeroStateSnapshot();
  for (const value of Object.values(state)) {
    if (value !== 0) throw new Error("Guest QA database is not at zero state");
  }
  return state;
}

export function ownerSnapshot(userId: string): OwnerSnapshot {
  const owner = requireUuid(userId, "owner");
  return psqlJson<OwnerSnapshot>(`
    select json_build_object(
      'conversations', (select count(*) from public.conversations where user_id = '${owner}'),
      'messages', (select count(*) from public.messages where user_id = '${owner}'),
      'user_messages', (select count(*) from public.messages where user_id = '${owner}' and role = 'user'),
      'assistant_messages', (select count(*) from public.messages where user_id = '${owner}' and role = 'assistant'),
      'jobs', (select count(*) from public.backtest_jobs where user_id = '${owner}'),
      'succeeded_jobs', (select count(*) from public.backtest_jobs where user_id = '${owner}' and status = 'succeeded'),
      'runs', (select count(*) from public.backtest_runs where user_id = '${owner}'),
      'completed_runs', (select count(*) from public.backtest_runs where user_id = '${owner}' and status = 'completed'),
      'ideas', (select count(*) from public.ideas where user_id = '${owner}'),
      'idea_versions', (select count(*) from public.idea_versions where user_id = '${owner}'),
      'evidence', (select count(*) from public.evidence_artifacts where user_id = '${owner}'),
      'decisions', (select count(*) from public.decision_notes where user_id = '${owner}'),
      'feedback', (select count(*) from public.feedback where user_id = '${owner}'),
      'chat_units', coalesce((select sum(used_count) from public.usage_counters where user_id = '${owner}' and resource = 'chat_messages'), 0),
      'simulation_units', coalesce((select sum(used_count) from public.usage_counters where user_id = '${owner}' and resource = 'backtest_runs'), 0),
      'feedback_units', coalesce((select sum(used_count) from public.usage_counters where user_id = '${owner}' and resource = 'feedback'), 0),
      'route_receipts', (select count(*) from public.route_receipts where user_id = '${owner}'),
      'cost_rows', (select count(*) from public.cost_ledger_entries where user_id = '${owner}'),
      'provider_cost_usd', coalesce((select sum(cost_amount) from public.cost_ledger_entries where user_id = '${owner}' and status = 'succeeded'), 0),
      'provider_latency_ms', coalesce((select sum(latency_ms) from public.cost_ledger_entries where user_id = '${owner}' and status = 'succeeded'), 0),
      'expires_at', (select expires_at::text from public.guest_workspaces where user_id = '${owner}')
    )::text
  `);
}

export function resultSummaryCost(userId: string): {
  rows: number;
  cost_usd: number;
  latency_ms: number;
} {
  const owner = requireUuid(userId, "owner");
  return psqlJson<{ rows: number; cost_usd: number; latency_ms: number }>(`
    select json_build_object(
      'rows', count(*),
      'cost_usd', coalesce(sum(cost_amount), 0),
      'latency_ms', coalesce(sum(latency_ms), 0)
    )::text
    from public.cost_ledger_entries
    where user_id = '${owner}'
      and task = 'result_summary'
      and status = 'succeeded'
  `);
}

export function resultTruthFingerprint(
  userId: string,
  conversationId: string,
): ResultTruthFingerprint {
  const owner = requireUuid(userId, "owner");
  const conversation = requireUuid(conversationId, "conversation");
  return psqlJson<ResultTruthFingerprint>(`
    select json_build_object(
      'rows', count(*),
      'fingerprint', md5(
        coalesce(
          jsonb_agg(
            jsonb_build_object(
              'id', id,
              'strategy_id', strategy_id,
              'status', status,
              'asset_class', asset_class,
              'symbols', symbols,
              'allocation_method', allocation_method,
              'benchmark_symbol', benchmark_symbol,
              'config_snapshot', config_snapshot,
              'metrics', metrics,
              'conversation_result_card', conversation_result_card,
              'chart', chart,
              'trades', trades,
              'error', error
            )
            order by id
          )::text,
          '[]'
        )
      )
    )::text
    from public.backtest_runs
    where user_id = '${owner}'
      and conversation_id = '${conversation}'
  `);
}

export function conversationGraph(
  userId: string,
  conversationId: string,
): ConversationGraph {
  const owner = requireUuid(userId, "owner");
  const conversation = requireUuid(conversationId, "conversation");
  return psqlJson<ConversationGraph>(`
    select json_build_object(
      'conversation', coalesce((select json_agg(id::text order by id) from public.conversations where id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'messages', coalesce((select json_agg(id::text order by id) from public.messages where conversation_id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'strategies', coalesce((select json_agg(id::text order by id) from public.strategies where conversation_id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'jobs', coalesce((select json_agg(id::text order by id) from public.backtest_jobs where conversation_id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'runs', coalesce((select json_agg(id::text order by id) from public.backtest_runs where conversation_id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'ideas', coalesce((select json_agg(id::text order by id) from public.ideas where source_conversation_id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'idea_versions', coalesce((select json_agg(id::text order by id) from public.idea_versions where source_conversation_id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'evidence', coalesce((select json_agg(id::text order by id) from public.evidence_artifacts where source_conversation_id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'decisions', coalesce((select json_agg(id::text order by id) from public.decision_notes where source_conversation_id = '${conversation}' and user_id = '${owner}'), '[]'::json),
      'context_packets', coalesce((select json_agg(id::text order by id) from public.context_packets where user_id = '${owner}'), '[]'::json),
      'run_context_packets', coalesce((
        select json_agg(link.id::text order by link.id)
        from public.run_context_packets as link
        join public.backtest_runs as run on run.id = link.run_id
        where link.user_id = '${owner}'
          and run.conversation_id = '${conversation}'
      ), '[]'::json),
      'checkpoints', coalesce((select json_agg(checkpoint_id order by checkpoint_id) from public.checkpoints where thread_id = '${conversation}'), '[]'::json),
      'checkpoint_blobs', coalesce((
        select json_agg(
          concat_ws(':', checkpoint_ns, channel, version)
          order by checkpoint_ns, channel, version
        )
        from public.checkpoint_blobs
        where thread_id = '${conversation}'
      ), '[]'::json),
      'checkpoint_writes', coalesce((
        select json_agg(
          concat_ws(':', checkpoint_ns, checkpoint_id, task_id, idx)
          order by checkpoint_ns, checkpoint_id, task_id, idx
        )
        from public.checkpoint_writes
        where thread_id = '${conversation}'
      ), '[]'::json)
    )::text
  `);
}

export function sameGraphIds(
  before: ConversationGraph,
  after: ConversationGraph,
): boolean {
  return (Object.keys(before) as Array<keyof ConversationGraph>).every(
    (key) =>
      JSON.stringify([...before[key]].sort()) ===
      JSON.stringify([...after[key]].sort()),
  );
}

export function graphDuplicateCount(graph: ConversationGraph): number {
  return (Object.keys(graph) as Array<keyof ConversationGraph>).reduce(
    (total, key) => total + graph[key].length - new Set(graph[key]).size,
    0,
  );
}

export function markWorkspaceExpired(userId: string): void {
  const owner = requireUuid(userId, "owner");
  const changed = psqlJson<{ ok: boolean }>(`
    begin;
    alter table public.guest_workspaces
      disable trigger protect_guest_workspace_policy_fields;
    with changed as (
      update public.guest_workspaces
         set created_at = now() - interval '7 days 20 minutes',
             expires_at = now() - interval '20 minutes',
             updated_at = now() - interval '20 minutes'
       where user_id = '${owner}'
       returning 1
    )
    select json_build_object('ok', exists(select 1 from changed))::text;
    alter table public.guest_workspaces
      enable trigger protect_guest_workspace_policy_fields;
    commit;
  `);
  if (!changed.ok) {
    throw new Error("Local guest QA expiry fixture was incomplete");
  }
}

export function guestWorkspaceExpiryIsImmutable(userId: string): boolean {
  const owner = requireUuid(userId, "immutable workspace owner");
  try {
    psqlJson<{ changed: boolean }>(`
      with changed as (
        update public.guest_workspaces
           set expires_at = expires_at + interval '1 microsecond'
         where user_id = '${owner}'
         returning 1
      )
      select json_build_object(
        'changed',
        exists(select 1 from changed)
      )::text
    `);
    return false;
  } catch {
    return true;
  }
}

export function markClaimedWorkspaceCleanupReady(userId: string): void {
  const owner = requireUuid(userId, "claimed guest owner");
  const changed = psqlJson<{ ok: boolean }>(`
    with changed as (
      update public.guest_workspaces
         set claimed_at = now() - interval '20 minutes',
             updated_at = now() - interval '20 minutes'
       where user_id = '${owner}'
         and status = 'claimed'
         and claimed_by is not null
       returning 1
    )
    select json_build_object('ok', exists(select 1 from changed))::text
  `);
  if (!changed.ok) {
    throw new Error("Claimed guest cleanup fixture was incomplete");
  }
}

export function cleanupExpectedGuestCandidates(userIds: string[]): {
  dry_run_count: number;
  deleted_count: number;
  claimed_identity_count: number;
  expired_workspace_count: number;
} {
  if (userIds.length < 1 || userIds.length > 100) {
    throw new Error("Cleanup fixture must contain between one and 100 owners");
  }
  const expected = userIds.map((value) => requireUuid(value, "cleanup owner"));
  const expectedSet = new Set(expected);
  if (expectedSet.size !== expected.length) {
    throw new Error("Cleanup fixture owners must be unique");
  }
  const dryRun = psqlJson<Array<{ user_id: string; cleanup_reason: string }>>(`
    select coalesce(
      json_agg(
        json_build_object(
          'user_id', user_id,
          'cleanup_reason', cleanup_reason
        )
      ),
      '[]'::json
    )::text
    from public.claim_expired_guest_workspaces(${expected.length}, true)
  `);
  if (
    dryRun.length !== expected.length ||
    dryRun.some((row) => !expectedSet.has(row.user_id))
  ) {
    throw new Error("Cleanup dry run did not select the exact fixture set");
  }
  const claimed = psqlJson<
    Array<{
      user_id: string;
      auth_deleted: boolean;
      cleanup_reason: string;
    }>
  >(`
    select coalesce(
      json_agg(
        json_build_object(
          'user_id', user_id,
          'auth_deleted', auth_deleted,
          'cleanup_reason', cleanup_reason
        )
      ),
      '[]'::json
    )::text
    from public.claim_expired_guest_workspaces(${expected.length}, false)
  `);
  if (
    claimed.length !== expected.length ||
    claimed.some(
      (row) => !expectedSet.has(row.user_id) || row.auth_deleted !== true,
    )
  ) {
    throw new Error("Cleanup claim did not match the bounded dry run");
  }
  return {
    dry_run_count: dryRun.length,
    deleted_count: claimed.length,
    claimed_identity_count: claimed.filter(
      (row) => row.cleanup_reason === "claimed_identity",
    ).length,
    expired_workspace_count: claimed.filter(
      (row) => row.cleanup_reason === "expired_workspace",
    ).length,
  };
}

export function cleanupOneExpiredGuest(): {
  dry_run_count: number;
  deleted_count: number;
} {
  assertExactLocalCandidate();
  const dryRun = psqlJson<Array<{ user_id: string }>>(`
    select coalesce(json_agg(json_build_object('user_id', user_id)), '[]'::json)::text
    from public.claim_expired_guest_workspaces(1, true)
  `);
  if (dryRun.length !== 1) {
    throw new Error("Cleanup dry run did not select exactly one fixture");
  }
  const claimed = psqlJson<Array<{ user_id: string; auth_deleted: boolean }>>(`
    select coalesce(
      json_agg(json_build_object('user_id', user_id, 'auth_deleted', auth_deleted)),
      '[]'::json
    )::text
    from public.claim_expired_guest_workspaces(1, false)
  `);
  if (
    claimed.length !== 1 ||
    claimed[0].user_id !== dryRun[0].user_id ||
    claimed[0].auth_deleted !== true
  ) {
    throw new Error("Cleanup claim did not match the bounded dry run");
  }
  return { dry_run_count: 1, deleted_count: 1 };
}

export function authUserExists(userId: string): boolean {
  const owner = requireUuid(userId, "owner");
  return psqlJson<{ exists: boolean }>(`
    select json_build_object(
      'exists',
      exists(select 1 from auth.users where id = '${owner}')
    )::text
  `).exists;
}

export function handoffCount(userId: string): number {
  const owner = requireUuid(userId, "owner");
  return psqlJson<{ count: number }>(`
    select json_build_object(
      'count',
      (select count(*) from public.guest_workspace_handoffs where source_user_id = '${owner}')
    )::text
  `).count;
}

export function handoffState(userId: string): {
  total: number;
  consumed: number;
} {
  const owner = requireUuid(userId, "owner");
  return psqlJson<{ total: number; consumed: number }>(`
    select json_build_object(
      'total', count(*),
      'consumed', count(*) filter (where status = 'consumed')
    )::text
    from public.guest_workspace_handoffs
    where source_user_id = '${owner}'
  `);
}

export function decisionTargetsEvidence(params: {
  userId: string;
  conversationId: string;
  evidenceId: string;
}): boolean {
  const owner = requireUuid(params.userId, "owner");
  const conversation = requireUuid(params.conversationId, "conversation");
  const evidence = requireUuid(params.evidenceId, "evidence");
  return psqlJson<{ matches: boolean }>(`
    select json_build_object(
      'matches',
      exists(
        select 1
        from public.decision_notes
        where user_id = '${owner}'
          and source_conversation_id = '${conversation}'
          and evidence_artifact_id = '${evidence}'
      )
    )::text
  `).matches;
}

export function profileAccountKind(userId: string): {
  is_anonymous: boolean;
  email_present: boolean;
} {
  const owner = requireUuid(userId, "owner");
  return psqlJson<{ is_anonymous: boolean; email_present: boolean }>(`
    select json_build_object(
      'is_anonymous', coalesce((select is_anonymous from auth.users where id = '${owner}'), false),
      'email_present', exists(select 1 from public.profiles where id = '${owner}' and nullif(email, '') is not null)
    )::text
  `);
}

export function workspaceFacts(userId: string): {
  exists: boolean;
  active: boolean;
  fixed_seven_days: boolean;
  conversation_id: string | null;
  claimed_by: string | null;
} {
  const owner = requireUuid(userId, "owner");
  return psqlJson<{
    exists: boolean;
    active: boolean;
    fixed_seven_days: boolean;
    conversation_id: string | null;
    claimed_by: string | null;
  }>(`
    select json_build_object(
      'exists', exists(select 1 from public.guest_workspaces where user_id = '${owner}'),
      'active', exists(select 1 from public.guest_workspaces where user_id = '${owner}' and status = 'active' and expires_at > now()),
      'fixed_seven_days', exists(select 1 from public.guest_workspaces where user_id = '${owner}' and expires_at = created_at + interval '7 days'),
      'conversation_id', (select conversation_id::text from public.guest_workspaces where user_id = '${owner}'),
      'claimed_by', (select claimed_by::text from public.guest_workspaces where user_id = '${owner}')
    )::text
  `);
}

export function feedbackPrivacy(params: {
  userId: string;
  conversationId: string;
}): {
  rows: number;
  email_present: boolean;
  transcript_present: boolean;
  forbidden_context_fields: number;
  unchecked_rows: number;
  approved_context_rows: number;
  unapproved_key_rows: number;
  sensitive_value_rows: number;
} {
  const owner = requireUuid(params.userId, "owner");
  const conversation = requireUuid(
    params.conversationId,
    "feedback conversation",
  );
  return psqlJson<{
    rows: number;
    email_present: boolean;
    transcript_present: boolean;
    forbidden_context_fields: number;
    unchecked_rows: number;
    approved_context_rows: number;
    unapproved_key_rows: number;
    sensitive_value_rows: number;
  }>(`
    select json_build_object(
      'rows', count(*),
      'email_present', coalesce(bool_or(message ~* '[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}'), false),
      'transcript_present', coalesce(bool_or(context ? 'transcript' or context ? 'messages' or context ? 'raw_transcript'), false),
      'forbidden_context_fields', coalesce(sum(
        case when context ?| array['token','cookie','authorization','headers','email','url_query','transcript','messages'] then 1 else 0 end
      ), 0),
      'unchecked_rows', count(*) filter (where not (context ? 'conversation_id')),
      'approved_context_rows', count(*) filter (
        where context ->> 'conversation_id' = '${conversation}'
          and context ->> 'surface' = 'guest_header'
      ),
      'unapproved_key_rows', count(*) filter (
        where exists (
          select 1
          from jsonb_object_keys(context) as context_key(key)
          where context_key.key <> all(array[
            'source','surface','conversation_id','message_id','message_kind',
            'artifact_id','artifact_type','artifact_status','result_run_id',
            'strategy_id','saved_strategy_id','confirmation_id',
            'confirmation_state','confirmation_status','backtest_job_id',
            'backtest_job_status','failure_code','retryable','rating','tags',
            'timestamp','page_path','has_attachments','attachment_count'
          ])
        )
      ),
      'sensitive_value_rows', count(*) filter (
        where context::text ~* (
          'Preserved local QA idea'
          || '|The preserved local QA simulation completed'
          || '|[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}'
          || '|bearer|refresh[_ -]?token|cookie|authorization'
        )
      )
    )::text
    from public.feedback
    where user_id = '${owner}'
  `);
}

export function seedDurableRetryableFailure(params: {
  userId: string;
  conversationId: string;
}): {
  inserted: boolean;
  failedAssistantId: string;
} {
  const owner = requireUuid(params.userId, "failure owner");
  const conversation = requireUuid(
    params.conversationId,
    "failure conversation",
  );
  const userMessage = randomUUID();
  const assistantMessage = randomUUID();
  const prompt = "Retry this local QA recovery turn";
  const seeded = psqlJson<{ inserted: boolean }>(`
    with owned_conversation as (
      select 1
      from public.conversations
      where id = '${conversation}'
        and user_id = '${owner}'
    ),
    inserted_user as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata, created_at
      )
      select
        '${userMessage}', '${conversation}', '${owner}', 'user',
        '${prompt}', '{}'::jsonb, now()
      from owned_conversation
      returning 1
    ),
    inserted_assistant as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata, created_at
      )
      select
        '${assistantMessage}', '${conversation}', '${owner}', 'assistant',
        'Something went wrong. Your conversation is saved. Please try again.',
        jsonb_build_object(
          'conversation_mode', 'recovery',
          'agent_runtime_stage_outcome', 'agent_runtime_failure',
          'recovery', jsonb_build_object(
            'code', 'runtime_failure',
            'retryable', true,
            'language', 'en'
          ),
          'retry_last_turn', jsonb_build_object('message', '${prompt}')
        ),
        now() + interval '1 millisecond'
      from owned_conversation
      cross join inserted_user
      returning 1
    )
    select json_build_object(
      'inserted',
      exists(select 1 from inserted_user)
      and exists(select 1 from inserted_assistant)
    )::text
  `);
  if (!seeded.inserted) {
    throw new Error("Durable recovery fixture was not inserted");
  }
  return {
    inserted: true,
    failedAssistantId: assistantMessage,
  };
}

export function seedDistinctGuestConfirmation(params: {
  userId: string;
  conversationId: string;
  sourceMessageId: string;
}): {
  messageId: string;
  confirmationId: string;
} {
  const owner = requireUuid(params.userId, "confirmation owner");
  const conversation = requireUuid(
    params.conversationId,
    "confirmation conversation",
  );
  const sourceMessage = requireUuid(
    params.sourceMessageId,
    "source confirmation message",
  );
  const messageId = randomUUID();
  const confirmationId = `confirmation-${randomUUID()}`;
  const source = psqlJson<{
    metadata: Record<string, unknown> | null;
    workspace_active: boolean;
    completed_runs: number;
    simulation_units: number;
  }>(`
    select json_build_object(
      'metadata', (
        select metadata
        from public.messages
        where id = '${sourceMessage}'
          and user_id = '${owner}'
          and conversation_id = '${conversation}'
          and role = 'assistant'
      ),
      'workspace_active', exists(
        select 1
        from public.guest_workspaces as workspace
        join auth.users as auth_user on auth_user.id = workspace.user_id
        where workspace.user_id = '${owner}'
          and workspace.conversation_id = '${conversation}'
          and workspace.status = 'active'
          and workspace.expires_at > now()
          and auth_user.is_anonymous
      ),
      'completed_runs', (
        select count(*)
        from public.backtest_runs
        where user_id = '${owner}'
          and conversation_id = '${conversation}'
          and status = 'completed'
      ),
      'simulation_units', coalesce((
        select sum(used_count)
        from public.usage_counters
        where user_id = '${owner}'
          and resource = 'backtest_runs'
      ), 0)
    )::text
  `);
  if (
    !source.metadata ||
    !source.workspace_active ||
    ![1, 2].includes(source.completed_runs) ||
    source.simulation_units < source.completed_runs ||
    source.simulation_units > 2
  ) {
    throw new Error(
      "Distinct guest confirmation requires an active owner with settled runs",
    );
  }
  const metadata = rekeyGuestQaConfirmationMetadata(
    source.metadata,
    confirmationId,
  );
  const encodedMetadata = Buffer.from(
    JSON.stringify(metadata),
    "utf8",
  ).toString("base64");
  const seeded = psqlJson<{ inserted: boolean }>(`
    with owned_source as (
      select 1
      from public.messages as message
      join public.guest_workspaces as workspace
        on workspace.user_id = message.user_id
       and workspace.conversation_id = message.conversation_id
      join auth.users as auth_user on auth_user.id = workspace.user_id
      where message.id = '${sourceMessage}'
        and message.user_id = '${owner}'
        and message.conversation_id = '${conversation}'
        and message.role = 'assistant'
        and workspace.status = 'active'
        and workspace.expires_at > now()
        and auth_user.is_anonymous
        and message.metadata -> 'confirmation_payload' -> 'validation'
          ->> 'executable' = 'true'
        and message.metadata -> 'confirmation_card' ->> 'status'
          = 'ready_to_run'
        and (
          select count(*)
          from jsonb_array_elements(
            coalesce(
              message.metadata -> 'confirmation_card' -> 'actions',
              '[]'::jsonb
            )
          ) as action
          where action ->> 'type' = 'run_backtest'
        ) = 1
        and (
          select count(*)
          from public.backtest_runs
          where user_id = '${owner}'
            and conversation_id = '${conversation}'
            and status = 'completed'
        ) between 1 and 2
        and coalesce((
          select sum(used_count)
          from public.usage_counters
          where user_id = '${owner}'
            and resource = 'backtest_runs'
        ), 0) between 1 and 2
    ),
    inserted_confirmation as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata, created_at
      )
      select
        '${messageId}', '${conversation}', '${owner}', 'assistant',
        'A distinct local QA confirmation is ready.',
        convert_from(decode('${encodedMetadata}', 'base64'), 'UTF8')::jsonb,
        (
          select coalesce(max(created_at), now()) + interval '1 millisecond'
          from public.messages
          where conversation_id = '${conversation}'
        )
      from owned_source
      returning 1
    )
    select json_build_object(
      'inserted',
      exists(select 1 from inserted_confirmation)
    )::text
  `);
  if (!seeded.inserted) {
    throw new Error("Distinct guest confirmation fixture was not inserted");
  }
  return { messageId, confirmationId };
}

export function seedGuestSimulationExhaustionFixture(params: {
  userId: string;
  conversationId: string;
}): {
  sourceMessageId: string;
  confirmationId: string;
} {
  const owner = requireUuid(params.userId, "simulation fixture owner");
  const conversation = requireUuid(
    params.conversationId,
    "simulation fixture conversation",
  );
  const strategyId = randomUUID();
  const runId = randomUUID();
  const sourceMessageId = randomUUID();
  const resultMessageId = randomUUID();
  const confirmationId = `confirmation-${randomUUID()}`;
  const visitorKey = `visitor:${createHmac(
    "sha256",
    process.env.CUADRAO_VISITOR_KEY_SECRET ?? "argus-visitor-key",
  )
    .update("127.0.0.1")
    .digest("hex")
    .slice(0, 32)}`;
  const resultCard = {
    title: "MSFT buy and hold",
    symbols: ["MSFT"],
    strategy_label: "Buy and hold",
    asset_class: "equity",
    date_range: {
      start: "2025-07-25",
      end: "2026-07-24",
      display: "July 25, 2025 to July 24, 2026",
    },
    status_label: "Simulation Complete",
    rows: [
      { key: "ending_value", label: "Ending value", value: "$11,120" },
      { key: "total_return_pct", label: "Total return", value: "+11.2%" },
      {
        key: "benchmark_delta_pct",
        label: "Vs benchmark",
        value: "+2.1 pts",
      },
      {
        key: "max_drawdown_pct",
        label: "Max drawdown",
        value: "-7.4%",
      },
    ],
    assumptions: [
      "$10,000 starting capital",
      "Long-only, equal-weight run",
      "No fees or slippage",
      "Benchmark: SPY",
    ],
    actions: [],
    chart: {
      kind: "portfolio_equity",
      currency: "USD",
      base_value: 10_000,
      series: [
        { time: "2025-07-25", value: 10_000 },
        { time: "2025-10-24", value: 10_380 },
        { time: "2026-01-23", value: 10_120 },
        { time: "2026-04-24", value: 10_760 },
        { time: "2026-07-24", value: 11_120 },
      ],
    },
  };
  const metadata = {
    confirmation_payload: {
      confirmation_id: confirmationId,
      artifact_id: confirmationId,
      strategy: {
        asset_universe: ["MSFT"],
        date_range: {
          start: "2025-07-25",
          end: "2026-07-24",
        },
      },
      launch_payload: {
        symbols: ["MSFT"],
        benchmark_symbol: "SPY",
        requested_date_range: {
          start: "2025-07-25",
          end: "2026-07-25",
        },
      },
      validation: {
        status: "ready_to_run",
        executable: true,
      },
    },
    confirmation_card: {
      confirmation_id: confirmationId,
      confirmation_state: "active",
      status: "ready_to_run",
      title: "MSFT compared with SPY",
      actions: [
        {
          type: "run_backtest",
          label: "Run backtest",
          payload: {
            confirmation_id: confirmationId,
            artifact_id: confirmationId,
            idempotency_key: confirmationId,
          },
        },
      ],
    },
    active_confirmation_reference: {
      artifact_id: confirmationId,
      metadata: { confirmation_id: confirmationId },
    },
    artifact_references: [
      {
        artifact_id: confirmationId,
        metadata: { confirmation_id: confirmationId },
      },
    ],
  };
  const encodedMetadata = Buffer.from(
    JSON.stringify(metadata),
    "utf8",
  ).toString("base64");
  const encodedResultCard = Buffer.from(
    JSON.stringify(resultCard),
    "utf8",
  ).toString("base64");
  const seeded = psqlJson<{ ok: boolean }>(`
    with active_owner as (
      select workspace.created_at, workspace.expires_at
      from public.guest_workspaces as workspace
      join auth.users as auth_user on auth_user.id = workspace.user_id
      join public.conversations as conversation
        on conversation.id = workspace.conversation_id
       and conversation.user_id = workspace.user_id
      where workspace.user_id = '${owner}'
        and workspace.conversation_id = '${conversation}'
        and workspace.status = 'active'
        and workspace.expires_at > now()
        and auth_user.is_anonymous
    ),
    inserted_strategy as (
      insert into public.strategies (
        id, user_id, conversation_id, name, template, asset_class,
        symbols, benchmark_symbol
      )
      select
        '${strategyId}', '${owner}', '${conversation}',
        'Guest QA exhausted simulation', 'buy_and_hold', 'equity',
        array['MSFT']::text[], 'SPY'
      from active_owner
      returning 1
    ),
    inserted_run as (
      insert into public.backtest_runs (
        id, user_id, conversation_id, strategy_id, status, asset_class,
        symbols, benchmark_symbol, config_snapshot, conversation_result_card
      )
      select
        '${runId}', '${owner}', '${conversation}', '${strategyId}',
        'completed', 'equity', array['MSFT']::text[], 'SPY',
        jsonb_build_object(
          'template', 'buy_and_hold',
          'symbols', jsonb_build_array('MSFT'),
          'benchmark_symbol', 'SPY'
        ),
        convert_from(
          decode('${encodedResultCard}', 'base64'),
          'UTF8'
        )::jsonb
      from inserted_strategy
      returning 1
    ),
    inserted_source as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata
      )
      select
        '${sourceMessageId}', '${conversation}', '${owner}', 'assistant',
        'A local QA confirmation is ready.',
        convert_from(decode('${encodedMetadata}', 'base64'), 'UTF8')::jsonb
      from inserted_run
      returning 1
    ),
    inserted_result as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata
      )
      select
        '${resultMessageId}', '${conversation}', '${owner}', 'assistant',
        'The local QA simulation completed.',
        jsonb_build_object(
          'result_run_id', '${runId}',
          'latest_run_id', '${runId}',
          'result_strategy_id', '${strategyId}',
          'result_conversation_id', '${conversation}',
          'result_card',
            convert_from(
              decode('${encodedResultCard}', 'base64'),
              'UTF8'
            )::jsonb
        )
      from inserted_source
      returning 1
    ),
    inserted_usage as (
      insert into public.usage_counters (
        user_id, resource, period, period_start, period_end,
        used_count, limit_count
      )
      select
        '${owner}', 'backtest_runs', 'guest_session',
        active_owner.created_at, active_owner.expires_at, 2, 2
      from active_owner
      cross join inserted_result
      returning 1
    ),
    inserted_visitor_usage as (
      insert into public.visitor_usage_counters (
        visitor_key, resource, period, period_start, period_end,
        used_count, limit_count
      )
      values (
        '${visitorKey}', 'backtest_runs', 'day', date_trunc('day', now()),
        date_trunc('day', now()) + interval '1 day', 2, 2
      )
      on conflict (visitor_key, resource, period, period_start) do update
      set
        period_end = excluded.period_end,
        used_count = excluded.used_count,
        limit_count = excluded.limit_count,
        updated_at = now()
      returning 1
    )
    select json_build_object(
      'ok',
      exists(select 1 from inserted_strategy)
      and exists(select 1 from inserted_run)
      and exists(select 1 from inserted_source)
      and exists(select 1 from inserted_usage)
      and exists(select 1 from inserted_visitor_usage)
    )::text
  `);
  if (!seeded.ok) {
    throw new Error("Guest simulation exhaustion fixture was incomplete");
  }
  return { sourceMessageId, confirmationId };
}

export function seedGuestResolvedClarificationRailHistory(params: {
  userId: string;
  conversationId: string;
}): { clarificationMessageId: string } {
  const owner = requireUuid(params.userId, "rail history owner");
  const conversation = requireUuid(
    params.conversationId,
    "rail history conversation",
  );
  const clarificationMessageId = randomUUID();
  const records = [
    {
      id: randomUUID(),
      role: "assistant",
      content: "Reviewing the first result.",
      metadata: {},
    },
    {
      id: randomUUID(),
      role: "user",
      content: "Show me the assumptions.",
      metadata: {},
    },
    {
      id: randomUUID(),
      role: "assistant",
      content: "The run uses daily data.",
      metadata: {},
    },
    {
      id: randomUUID(),
      role: "user",
      content: "Keep the benchmark.",
      metadata: {},
    },
    {
      id: randomUUID(),
      role: "assistant",
      content: "SPY remains the benchmark.",
      metadata: {},
    },
    {
      id: randomUUID(),
      role: "user",
      content: "Try another idea.",
      metadata: {},
    },
    {
      id: randomUUID(),
      role: "assistant",
      content: "Tell me which asset to use.",
      metadata: {},
    },
    {
      id: clarificationMessageId,
      role: "assistant",
      content: "Which asset should I test?",
      metadata: {
        clarification: {
          kind: "clarification",
          prompt_source: "degraded_fallback",
          requested_field: "asset_universe",
          semantic_needs: ["asset_target"],
        },
        pending_strategy: {
          requested_field: "asset_universe",
          strategy: {
            strategy_type: "buy_and_hold",
            date_range: "past year",
            capital_amount: 10_000,
            extra_parameters: {
              date_range_raw_text: "past year",
              requested_date_range: {
                start: "2025-07-26",
                end: "2026-07-26",
              },
            },
          },
        },
      },
    },
    { id: randomUUID(), role: "user", content: "AAPL", metadata: {} },
  ].map((record, index) => ({ ...record, offset_ms: index + 1 }));
  const encodedRecords = Buffer.from(
    JSON.stringify(records),
    "utf8",
  ).toString("base64");
  const seeded = psqlJson<{ inserted: number }>(`
    with active_owner as (
      select 1
      from public.guest_workspaces as workspace
      join auth.users as auth_user on auth_user.id = workspace.user_id
      join public.conversations as conversation
        on conversation.id = workspace.conversation_id
       and conversation.user_id = workspace.user_id
      where workspace.user_id = '${owner}'
        and workspace.conversation_id = '${conversation}'
        and workspace.status = 'active'
        and workspace.expires_at > now()
        and auth_user.is_anonymous
        and (
          select count(*)
          from public.backtest_runs
          where user_id = '${owner}'
            and conversation_id = '${conversation}'
            and status = 'completed'
        ) = 1
    ),
    baseline as (
      select coalesce(max(created_at), now()) as created_at
      from public.messages
      where conversation_id = '${conversation}'
        and user_id = '${owner}'
    ),
    fixture_rows as (
      select *
      from jsonb_to_recordset(
        convert_from(decode('${encodedRecords}', 'base64'), 'UTF8')::jsonb
      ) as item(
        id uuid,
        role text,
        content text,
        metadata jsonb,
        offset_ms integer
      )
    ),
    inserted as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata, created_at
      )
      select
        fixture_rows.id,
        '${conversation}',
        '${owner}',
        fixture_rows.role,
        fixture_rows.content,
        fixture_rows.metadata,
        baseline.created_at
          + (fixture_rows.offset_ms || ' milliseconds')::interval
      from fixture_rows
      cross join active_owner
      cross join baseline
      returning 1
    )
    select json_build_object('inserted', count(*))::text
    from inserted
  `);
  if (seeded.inserted !== records.length) {
    throw new Error("Resolved Guest rail history fixture was incomplete");
  }
  return { clarificationMessageId };
}

export function seedGuestActiveConfirmationFixture(params: {
  userId: string;
  conversationId: string;
  symbol?: string;
  strategyPathId?: string;
}): {
  messageId: string;
  confirmationId: string;
} {
  const owner = requireUuid(params.userId, "confirmation fixture owner");
  const conversation = requireUuid(
    params.conversationId,
    "confirmation fixture conversation",
  );
  const messageId = randomUUID();
  const confirmationId = `confirmation-${randomUUID()}`;
  const symbol = params.symbol ?? "MSFT";
  const strategyPathId = params.strategyPathId
    ? requireUuid(params.strategyPathId, "confirmation fixture strategy path")
    : null;
  if (!/^[A-Z]{1,5}$/.test(symbol)) {
    throw new Error("Confirmation fixture symbol is invalid");
  }
  const actionPayload = {
    confirmation_id: confirmationId,
    artifact_id: confirmationId,
    conversation_id: conversation,
  };
  const metadata = {
    ...(strategyPathId ? { strategy_path_id: strategyPathId } : {}),
    confirmation_payload: {
      strategy: {
        strategy_type: "buy_and_hold",
        strategy_thesis: `Buy and hold ${symbol}.`,
        asset_universe: [symbol],
        asset_class: "equity",
        capital_amount: 10_000,
        date_range: {
          start: "2025-07-28",
          end: "2026-07-24",
        },
        extra_parameters: {
          date_range_raw_text: "past year",
          requested_date_range: {
            start: "2025-07-26",
            end: "2026-07-26",
          },
          effective_date_range: {
            start: "2025-07-28",
            end: "2026-07-24",
          },
        },
      },
      optional_parameters: {},
      launch_payload: {
        strategy_type: "buy_and_hold",
        symbol,
        symbols: [symbol],
        timeframe: "1D",
        date_range: {
          start: "2025-07-28",
          end: "2026-07-24",
        },
        requested_date_range: {
          start: "2025-07-26",
          end: "2026-07-26",
        },
        benchmark_symbol: "SPY",
        language: "en",
      },
      validation: {
        status: "ready_to_run",
        executable: true,
      },
    },
    confirmation_card: {
      confirmation_id: confirmationId,
      confirmation_state: "active",
      status: "ready_to_run",
      title: `${symbol} buy and hold`,
      rows: [
        { key: "strategy", label: "Strategy", value: "Buy and hold" },
        { key: "assets", label: "Assets", value: symbol },
        {
          key: "period",
          label: "Period",
          value: "July 28, 2025 to July 24, 2026",
        },
      ],
      display_facts: {
        timeframe: "1D",
        benchmark_symbol: "SPY",
      },
      assumptions: ["Benchmark: SPY"],
      actions: [
        {
          id: "run-backtest",
          type: "run_backtest",
          label: "Run backtest",
          presentation: "confirmation",
          payload: actionPayload,
        },
      ],
    },
    active_confirmation_reference: {
      artifact_kind: "confirmation",
      artifact_id: confirmationId,
      artifact_status: "active",
      metadata: {
        confirmation_id: confirmationId,
        artifact_type: "confirmation",
      },
    },
    artifact_references: [
      {
        artifact_kind: "confirmation",
        artifact_id: confirmationId,
        artifact_status: "active",
        metadata: {
          confirmation_id: confirmationId,
          artifact_type: "confirmation",
        },
      },
    ],
  };
  const encodedMetadata = Buffer.from(
    JSON.stringify(metadata),
    "utf8",
  ).toString("base64");
  const seeded = psqlJson<{ inserted: boolean }>(`
    with active_owner as (
      select 1
      from public.guest_workspaces as workspace
      join auth.users as auth_user on auth_user.id = workspace.user_id
      join public.conversations as conversation
        on conversation.id = workspace.conversation_id
       and conversation.user_id = workspace.user_id
      where workspace.user_id = '${owner}'
        and workspace.conversation_id = '${conversation}'
        and workspace.status = 'active'
        and workspace.expires_at > now()
        and auth_user.is_anonymous
        and (
          select count(*)
          from public.backtest_runs
          where user_id = '${owner}'
            and conversation_id = '${conversation}'
            and status = 'completed'
        ) = 1
        and coalesce((
          select sum(used_count)
          from public.usage_counters
          where user_id = '${owner}'
            and resource = 'backtest_runs'
        ), 0) = 2
    ),
    inserted_confirmation as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata, created_at
      )
      select
        '${messageId}', '${conversation}', '${owner}', 'assistant',
        'A deterministic local QA confirmation is ready.',
        convert_from(decode('${encodedMetadata}', 'base64'), 'UTF8')::jsonb,
        (
          select coalesce(max(created_at), now()) + interval '1 millisecond'
          from public.messages
          where conversation_id = '${conversation}'
        )
      from active_owner
      returning 1
    )
    select json_build_object(
      'inserted',
      exists(select 1 from inserted_confirmation)
    )::text
  `);
  if (!seeded.inserted) {
    throw new Error("Active guest confirmation fixture was not inserted");
  }
  return { messageId, confirmationId };
}

export function seedClaimSourceResultFixture(params: {
  userId: string;
  conversationId: string;
}): void {
  const owner = requireUuid(params.userId, "claim source owner");
  const conversation = requireUuid(
    params.conversationId,
    "claim source conversation",
  );
  const strategy = randomUUID();
  const run = randomUUID();
  const assistantMessage = randomUUID();
  const seeded = psqlJson<{ ok: boolean }>(`
    with owned_conversation as (
      select 1
      from public.conversations
      where id = '${conversation}'
        and user_id = '${owner}'
    ),
    inserted_strategy as (
      insert into public.strategies (
        id, user_id, conversation_id, name, template, asset_class,
        symbols, benchmark_symbol
      )
      select
        '${strategy}', '${owner}', '${conversation}',
        'Guest QA claim source', 'buy_and_hold', 'equity',
        array['MSFT']::text[], 'SPY'
      from owned_conversation
      returning 1
    ),
    inserted_run as (
      insert into public.backtest_runs (
        id, user_id, conversation_id, strategy_id, status, asset_class,
        symbols, benchmark_symbol, config_snapshot, conversation_result_card
      )
      select
        '${run}', '${owner}', '${conversation}', '${strategy}', 'completed',
        'equity', array['MSFT']::text[], 'SPY', '{}'::jsonb,
        jsonb_build_object(
          'status', 'completed',
          'symbols', jsonb_build_array('MSFT'),
          'benchmark_symbol', 'SPY'
        )
      from inserted_strategy
      returning 1
    ),
    inserted_message as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata
      )
      select
        '${assistantMessage}', '${conversation}', '${owner}', 'assistant',
        'Completed local claim source.',
        jsonb_build_object(
          'result_run_id', '${run}',
          'result_card', jsonb_build_object(
            'status', 'completed',
            'symbols', jsonb_build_array('MSFT'),
            'benchmark_symbol', 'SPY'
          )
        )
      from inserted_run
      returning 1
    )
    select json_build_object(
      'ok',
      exists(select 1 from inserted_strategy)
      and exists(select 1 from inserted_run)
      and exists(select 1 from inserted_message)
    )::text
  `);
  if (!seeded.ok) {
    throw new Error("Local claim source fixture was incomplete");
  }
}

export function seedClaimGraphFromConversation(params: {
  sourceOwnerId: string;
  sourceConversationId: string;
  targetOwnerId: string;
  includeCleanupEvidence?: boolean;
}): {
  conversationId: string;
  evidenceId: string;
  feedbackId: string;
  routeReceiptId: string;
  costLedgerId: string;
} {
  const sourceOwner = requireUuid(params.sourceOwnerId, "source owner");
  const sourceConversation = requireUuid(
    params.sourceConversationId,
    "source conversation",
  );
  const targetOwner = requireUuid(params.targetOwnerId, "target owner");
  const includeCleanupEvidence =
    params.includeCleanupEvidence === true ? "true" : "false";
  const ids = {
    conversation: randomUUID(),
    userMessage: randomUUID(),
    assistantMessage: randomUUID(),
    strategy: randomUUID(),
    run: randomUUID(),
    job: randomUUID(),
    idea: randomUUID(),
    version: randomUUID(),
    evidence: randomUUID(),
    decisionEvidence: randomUUID(),
    decision: randomUUID(),
    contextPacket: randomUUID(),
    runContextPacket: randomUUID(),
    feedback: randomUUID(),
    routeReceipt: randomUUID(),
    costLedger: randomUUID(),
  };
  const resultCardExpression = `
    jsonb_set(
      jsonb_set(source_run.conversation_result_card, '{evidenceArtifactId}', to_jsonb('${ids.evidence}'::text), true),
      '{evidence_artifact_id}', to_jsonb('${ids.evidence}'::text), true
    )
  `;
  const seeded = psqlJson<{ ok: boolean }>(`
    with source_run as (
      select *
      from public.backtest_runs
      where user_id = '${sourceOwner}'
        and conversation_id = '${sourceConversation}'
        and status = 'completed'
      order by created_at desc
      limit 1
    ),
    source_result_message as (
      select *
      from public.messages
      where user_id = '${sourceOwner}'
        and conversation_id = '${sourceConversation}'
        and metadata ? 'result_card'
      order by created_at desc
      limit 1
    ),
    inserted_conversation as (
      insert into public.conversations (
        id, user_id, title, title_source, language, last_message_preview
      ) values (
        '${ids.conversation}', '${targetOwner}', 'Guest QA preserved result',
        'system_default', 'en', 'Preserved result'
      )
      returning 1
    ),
    linked_workspace as (
      update public.guest_workspaces
         set conversation_id = '${ids.conversation}',
             updated_at = now()
       where user_id = '${targetOwner}'
       returning 1
    ),
    inserted_user_message as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata
      ) values (
        '${ids.userMessage}', '${ids.conversation}', '${targetOwner}',
        'user', 'Preserved local QA idea', '{}'::jsonb
      )
      returning 1
    ),
    inserted_strategy as (
      insert into public.strategies (
        id, user_id, conversation_id, name, template, asset_class,
        symbols, benchmark_symbol
      )
      select
        '${ids.strategy}', '${targetOwner}', '${ids.conversation}',
        'Preserved local QA strategy', 'buy_and_hold',
        source_run.asset_class, source_run.symbols, source_run.benchmark_symbol
      from source_run
      returning 1
    ),
    inserted_run as (
      insert into public.backtest_runs (
        id, user_id, conversation_id, strategy_id, status, asset_class,
        symbols, benchmark_symbol, config_snapshot, conversation_result_card
      )
      select
        '${ids.run}', '${targetOwner}', '${ids.conversation}',
        '${ids.strategy}', 'completed', source_run.asset_class,
        source_run.symbols, source_run.benchmark_symbol,
        source_run.config_snapshot, ${resultCardExpression}
      from source_run
      returning 1
    ),
    inserted_job as (
      insert into public.backtest_jobs (
        id, user_id, conversation_id, request_message_id,
        confirmation_message_id, idempotency_key, payload_hash,
        launch_payload, status, result_run_id
      ) values (
        '${ids.job}', '${targetOwner}', '${ids.conversation}',
        '${ids.userMessage}', '${ids.userMessage}',
        'guest-qa-preserved-run', 'guest-qa-preserved-payload',
        '{}'::jsonb, 'succeeded', '${ids.run}'
      )
      returning 1
    ),
    inserted_idea as (
      insert into public.ideas (
        id, user_id, source_conversation_id, title, summary, lifecycle
      ) values (
        '${ids.idea}', '${targetOwner}', '${ids.conversation}',
        'Preserved local QA idea', 'Preserved for atomic claim', 'reviewed'
      )
      returning 1
    ),
    inserted_version as (
      insert into public.idea_versions (
        id, user_id, idea_id, source_conversation_id, source_run_id,
        canonical_spec, strategy_snapshot, title, summary, lifecycle
      ) values (
        '${ids.version}', '${targetOwner}', '${ids.idea}',
        '${ids.conversation}', '${ids.run}', '{}'::jsonb, '{}'::jsonb,
        'Preserved local QA idea', 'Version one', 'reviewed'
      )
      returning 1
    ),
    inserted_evidence as (
      insert into public.evidence_artifacts (
        id, user_id, idea_id, idea_version_id, source_conversation_id,
        source_run_id, lifecycle, title, digest, payload
      ) values (
        '${ids.evidence}', '${targetOwner}', '${ids.idea}', '${ids.version}',
        '${ids.conversation}', '${ids.run}', 'reviewed',
        'Preserved local QA result', 'local-qa-digest', '{}'::jsonb
      )
      returning 1
    ),
    inserted_decision_evidence as (
      insert into public.evidence_artifacts (
        id, user_id, idea_id, idea_version_id, source_conversation_id,
        source_run_id, lifecycle, title, digest, payload
      ) values (
        '${ids.decisionEvidence}', '${targetOwner}', '${ids.idea}',
        '${ids.version}', '${ids.conversation}', null, 'decided',
        'Preserved local QA prior decision', 'local-qa-decision-digest',
        '{}'::jsonb
      )
      returning 1
    ),
    inserted_decision as (
      insert into public.decision_notes (
        id, user_id, idea_id, idea_version_id, evidence_artifact_id,
        source_conversation_id, decision_state, note
      ) values (
        '${ids.decision}', '${targetOwner}', '${ids.idea}', '${ids.version}',
        '${ids.decisionEvidence}', '${ids.conversation}', 'watching',
        'Preserved prior decision'
      )
      returning 1
    ),
    inserted_context_packet as (
      insert into public.context_packets (
        id, user_id, provider, packet_type, retrieved_at
      ) values (
        '${ids.contextPacket}', '${targetOwner}', 'alpaca', 'news', now()
      )
      returning 1
    ),
    inserted_run_context_packet as (
      insert into public.run_context_packets (
        id, user_id, run_id, context_packet_id
      ) values (
        '${ids.runContextPacket}', '${targetOwner}', '${ids.run}',
        '${ids.contextPacket}'
      )
      returning 1
    ),
    inserted_assistant_message as (
      insert into public.messages (
        id, conversation_id, user_id, role, content, metadata
      )
      select
        '${ids.assistantMessage}', '${ids.conversation}', '${targetOwner}',
        'assistant', 'The preserved local QA simulation completed.',
        jsonb_set(
          jsonb_set(
            jsonb_set(
              jsonb_set(
                source_result_message.metadata,
                '{result_card}', ${resultCardExpression}, true
              ),
              '{result_run_id}', to_jsonb('${ids.run}'::text), true
            ),
            '{latest_run_id}', to_jsonb('${ids.run}'::text), true
          ),
          '{result_strategy_id}', to_jsonb('${ids.strategy}'::text), true
        )
      from source_result_message
      cross join source_run
      returning 1
    ),
    inserted_checkpoint as (
      insert into public.checkpoints (
        thread_id, checkpoint_ns, checkpoint_id, checkpoint
      ) values (
        '${ids.conversation}', '', 'guest-qa-preserved-checkpoint', '{}'::jsonb
      )
      returning 1
    ),
    inserted_checkpoint_blob as (
      insert into public.checkpoint_blobs (
        thread_id, checkpoint_ns, channel, version, type, blob
      )
      select
        '${ids.conversation}', '', 'messages', 'guest-qa-cleanup',
        'msgpack', null
      from inserted_checkpoint
      returning 1
    ),
    inserted_checkpoint_write as (
      insert into public.checkpoint_writes (
        thread_id, checkpoint_ns, checkpoint_id, task_id, idx,
        channel, type, blob
      )
      select
        '${ids.conversation}', '', 'guest-qa-preserved-checkpoint',
        'guest-qa-cleanup', 0, 'messages', 'msgpack', decode('01', 'hex')
      from inserted_checkpoint
      returning 1
    ),
    inserted_feedback as (
      insert into public.feedback (
        id, user_id, type, message, context
      )
      select
        '${ids.feedback}', '${targetOwner}', 'general',
        'Guest QA cleanup privacy sentinel', '{}'::jsonb
      from inserted_assistant_message
      where ${includeCleanupEvidence}
      returning 1
    ),
    inserted_route_receipt as (
      insert into public.route_receipts (
        id, user_id, conversation_id, run_id, message_id, task, tier, mode,
        latency_ms, outcome, context_packet_ids
      )
      select
        '${ids.routeReceipt}', '${targetOwner}', '${ids.conversation}',
        '${ids.run}', '${ids.assistantMessage}', 'interpretation',
        'structured', 'json_schema', 1, 'succeeded',
        array['${ids.contextPacket}']::text[]
      from inserted_assistant_message
      cross join inserted_run_context_packet
      where ${includeCleanupEvidence}
      returning 1
    ),
    inserted_cost_ledger as (
      insert into public.cost_ledger_entries (
        id, source, service, provider, feature_area, task, user_id,
        conversation_id, message_id, backtest_run_id, backtest_job_id,
        route_receipt_id, correlation_id, billable_unit, status
      )
      select
        '${ids.costLedger}', 'api_turn', 'openrouter', 'openrouter',
        'guest_cleanup_qa', 'cleanup_fixture', '${targetOwner}',
        '${ids.conversation}', '${ids.assistantMessage}', '${ids.run}',
        '${ids.job}', '${ids.routeReceipt}', 'guest-qa-cleanup',
        'request', 'succeeded'
      from inserted_route_receipt
      cross join inserted_job
      returning 1
    ),
    inserted_usage as (
      insert into public.usage_counters (
        user_id, resource, period, period_start, period_end,
        used_count, limit_count
      )
      select
        '${targetOwner}', resource, 'guest_session',
        workspace.created_at, workspace.expires_at, used_count, limit_count
      from public.guest_workspaces as workspace
      cross join (
        values
          ('chat_messages'::text, 1, 10),
          ('backtest_runs'::text, 1, 1)
      ) as policy(resource, used_count, limit_count)
      where workspace.user_id = '${targetOwner}'
        and ${includeCleanupEvidence}
      returning 1
    )
    select json_build_object(
      'ok',
      exists(select 1 from inserted_conversation)
      and exists(select 1 from linked_workspace)
      and exists(select 1 from inserted_user_message)
      and exists(select 1 from inserted_strategy)
      and exists(select 1 from inserted_run)
      and exists(select 1 from inserted_job)
      and exists(select 1 from inserted_idea)
      and exists(select 1 from inserted_version)
      and exists(select 1 from inserted_evidence)
      and exists(select 1 from inserted_decision_evidence)
      and exists(select 1 from inserted_decision)
      and exists(select 1 from inserted_context_packet)
      and exists(select 1 from inserted_run_context_packet)
      and exists(select 1 from inserted_assistant_message)
      and exists(select 1 from inserted_checkpoint)
      and exists(select 1 from inserted_checkpoint_blob)
      and exists(select 1 from inserted_checkpoint_write)
      and (
        not ${includeCleanupEvidence}
        or (
          exists(select 1 from inserted_feedback)
          and exists(select 1 from inserted_route_receipt)
          and exists(select 1 from inserted_cost_ledger)
          and (select count(*) from inserted_usage) = 2
        )
      )
    )::text
  `);
  if (!seeded.ok) {
    throw new Error("Local guest QA claim fixture was incomplete");
  }
  return {
    conversationId: ids.conversation,
    evidenceId: ids.evidence,
    feedbackId: ids.feedback,
    routeReceiptId: ids.routeReceipt,
    costLedgerId: ids.costLedger,
  };
}

export function cleanupRetentionState(params: {
  userId: string;
  feedbackId: string;
  routeReceiptId: string;
  costLedgerId: string;
}): CleanupRetentionState {
  const owner = requireUuid(params.userId, "cleanup owner");
  const feedback = requireUuid(params.feedbackId, "cleanup feedback");
  const receipt = requireUuid(params.routeReceiptId, "cleanup route receipt");
  const cost = requireUuid(params.costLedgerId, "cleanup cost ledger");
  return psqlJson<CleanupRetentionState>(`
    select json_build_object(
      'feedback_rows', (
        select count(*) from public.feedback where id = '${feedback}'
      ),
      'usage_rows', (
        select count(*) from public.usage_counters where user_id = '${owner}'
      ),
      'retained_route_rows', (
        select count(*) from public.route_receipts where id = '${receipt}'
      ),
      'attributed_route_rows', (
        select count(*)
        from public.route_receipts
        where id = '${receipt}'
          and (
            user_id is not null
            or conversation_id is not null
            or run_id is not null
            or message_id is not null
          )
      ),
      'retained_cost_rows', (
        select count(*) from public.cost_ledger_entries where id = '${cost}'
      ),
      'attributed_cost_rows', (
        select count(*)
        from public.cost_ledger_entries
        where id = '${cost}'
          and (
            user_id is not null
            or conversation_id is not null
            or message_id is not null
            or backtest_run_id is not null
            or backtest_job_id is not null
          )
      ),
      'retained_cost_route_links', (
        select count(*)
        from public.cost_ledger_entries
        where id = '${cost}' and route_receipt_id = '${receipt}'
      )
    )::text
  `);
}

export class BackendController {
  private process: ChildProcess | null = null;
  private publicAccountsEnabled = false;

  async start(
    publicAccountsEnabled: boolean,
    options: { openRouterApiKey?: string } = {},
  ): Promise<void> {
    await this.stop();
    this.publicAccountsEnabled = publicAccountsEnabled;
    this.process = spawn(
      "poetry",
      [
        "run",
        "uvicorn",
        "argus.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(LOCAL_API_PORT),
      ],
      {
        cwd: REPOSITORY_ROOT,
        env: {
          ...process.env,
          CUADRAO_GUEST_ACCESS_ENABLED: "true",
          CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED: String(publicAccountsEnabled),
          CUADRAO_MOCK_AUTH: "false",
          ...(options.openRouterApiKey !== undefined
            ? { OPENROUTER_API_KEY: options.openRouterApiKey }
            : {}),
        },
        stdio: "ignore",
      },
    );
    await expect
      .poll(
        async () => {
          if (this.process?.exitCode !== null) return "exited";
          const response = await fetch(`${LOCAL_API_BASE}/auth/session`).catch(
            () => null,
          );
          return response?.status === 200 || response?.status === 401;
        },
        {
          message: "local Argus API should become healthy",
          timeout: 90_000,
          intervals: [100, 250, 500, 1_000],
        },
      )
      .toBe(true);
  }

  async stop(): Promise<void> {
    const child = this.process;
    this.process = null;
    if (!child || child.exitCode !== null) return;
    child.kill("SIGTERM");
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        if (child.exitCode === null) child.kill("SIGKILL");
        resolve();
      }, 5_000);
      child.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
  }

  get flagsRestoredFalse(): boolean {
    return !this.publicAccountsEnabled;
  }
}

export async function waitForBackendHealthy(): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await fetch(`${LOCAL_API_BASE}/auth/session`).catch(
          () => null,
        );
        return response?.status === 200 || response?.status === 401;
      },
      {
        message: "local Argus API should answer",
        timeout: 90_000,
        intervals: [100, 250, 500, 1_000],
      },
    )
    .toBe(true);
}

export async function assertFreshContext(
  context: BrowserContext,
): Promise<void> {
  const storage = await context.storageState();
  expect(storage.cookies).toEqual([]);
  expect(storage.origins).toEqual([]);
  expect(context.serviceWorkers()).toEqual([]);
}

export async function apiJson<T>(
  request: APIRequestContext,
  pathname: string,
  options: {
    method?: "GET" | "POST" | "PATCH" | "DELETE";
    data?: unknown;
  } = {},
): Promise<{ status: number; body: T }> {
  const method = options.method ?? "GET";
  const response = await request.fetch(`${LOCAL_API_BASE}${pathname}`, {
    method,
    data: options.data,
  });
  let body: T;
  try {
    body = (await response.json()) as T;
  } catch {
    throw new Error("Local guest QA API returned an unexpected response");
  }
  return { status: response.status(), body };
}

export async function waitForMe(
  page: Page,
  timeoutMs = 60_000,
): Promise<GuestMe> {
  const response = await page.waitForResponse(
    (candidate) =>
      candidate.request().method() === "GET" &&
      new URL(candidate.url()).pathname.endsWith("/api/v1/me") &&
      candidate.status() === 200,
    { timeout: timeoutMs },
  );
  return (await response.json()) as GuestMe;
}

export async function freshGuest(
  page: Page,
  options: {
    timeoutMs?: number;
    language?: "en" | "es-419";
    onBootstrapOwner?: (owner: string) => void;
  } = {},
): Promise<GuestMe> {
  const timeoutMs = options.timeoutMs ?? 60_000;
  const captchaToken =
    process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN?.trim() ?? "";
  try {
    if (!captchaToken) {
      throw new Error("Local guest QA CAPTCHA token is missing");
    }
    const bootstrapResponse = await page.context().request.post(
      `${LOCAL_API_BASE}/auth/guest`,
      {
        data: { captcha_token: captchaToken, language: options.language ?? "en" },
        headers: { origin: LOCAL_APP_ORIGIN },
        timeout: timeoutMs,
      },
    );
    if (bootstrapResponse.status() !== 200) {
      throw new Error("Local guest QA bootstrap was rejected");
    }
    const payload = (await bootstrapResponse.json()) as {
      user?: { id?: unknown } | null;
    };
    const bootstrapOwner = requireUuid(
      typeof payload.user?.id === "string" ? payload.user.id : "",
      "guest bootstrap owner",
    );
    options.onBootstrapOwner?.(bootstrapOwner);

    const mePromise = waitForMe(page, timeoutMs);
    await page.goto("/chat", { waitUntil: "domcontentloaded" });
    const me = await mePromise;
    if (me.user.id !== bootstrapOwner) {
      throw new Error("Guest bootstrap and verified profile owners differ");
    }
    expect(new URL(page.url()).pathname).toBe("/chat");
    return me;
  } catch (error) {
    throw new Error("Guest public entry failed before authentication", {
      cause: error,
    });
  }
}

export function evidenceLabel(namespace: string, value: string): string {
  const candidate = requireCandidateSha();
  return createHash("sha256")
    .update(`argus-guest-qa:${candidate}:${namespace}:${value}`)
    .digest("hex")
    .slice(0, 20);
}

export function safeConfirmationEvidence(
  facts: ConfirmationFacts,
): SafeConfirmationEvidence {
  return {
    message_label: evidenceLabel("message", facts.messageId),
    confirmation_label: evidenceLabel("confirmation", facts.confirmationId),
    asset_universe: [...facts.assetUniverse],
    benchmark: facts.benchmark,
    requested_date_range: { ...facts.requestedDateRange },
    effective_date_range: { ...facts.effectiveDateRange },
  };
}

export function normalizeRoute(rawUrl: string): string {
  const url = new URL(rawUrl);
  return url.pathname.replace(UUID_PATTERN, ":id");
}

function sanitizedEndpoint(rawUrl: string, method: string): string {
  let route = "unknown";
  try {
    route = normalizeRoute(rawUrl)
      .replace(EMAIL_PATTERN, ":redacted")
      .replace(JWT_PATTERN, ":redacted");
  } catch {
    route = "unknown";
  } finally {
    UUID_PATTERN.lastIndex = 0;
    EMAIL_PATTERN.lastIndex = 0;
    JWT_PATTERN.lastIndex = 0;
  }
  return `${method.toUpperCase()} ${route}`;
}

function browserErrorCategory(
  event: BrowserSafetyDetail["event"],
  rawError: string,
  status?: number | null,
): string {
  if (typeof status === "number" && status >= 500) {
    return "http_server_error";
  }
  if (typeof status === "number" && status >= 400) {
    return "http_client_error";
  }
  const value = rawError.toLowerCase();
  if (
    value.includes("err_connection_refused") ||
    value.includes("connection refused")
  ) {
    return "connection_refused";
  }
  if (
    value.includes("err_connection_reset") ||
    value.includes("connection reset")
  ) {
    return "connection_reset";
  }
  if (value.includes("err_aborted") || value.includes("abort")) {
    return "aborted";
  }
  if (value.includes("timeout") || value.includes("timed out")) {
    return "timeout";
  }
  if (value.includes("hydration")) return "hydration_error";
  if (value.includes("fetch") || value.includes("network")) {
    return "network_error";
  }
  return event;
}

export function browserSafetyDetail(input: {
  event: BrowserSafetyDetail["event"];
  rawUrl?: string;
  method?: string;
  rawError?: string;
  status?: number | null;
  correlatedFault?: boolean;
  context: BrowserSafetyContext;
}): BrowserSafetyDetail {
  const isNetwork = input.event === "failed_request";
  const category = browserErrorCategory(
    input.event,
    input.rawError ?? "",
    input.status,
  );
  const controlledNetworkFailure = (() => {
    if (
      input.context.phase !== "fault_injection" ||
      input.event !== "failed_request" ||
      category !== "connection_refused" ||
      !input.rawUrl
    ) {
      return false;
    }
    try {
      const url = new URL(input.rawUrl);
      return (
        ["localhost", "127.0.0.1", "::1"].includes(url.hostname) &&
        url.port === String(LOCAL_API_PORT) &&
        url.pathname.startsWith("/api/v1/")
      );
    } catch {
      return false;
    }
  })();
  const controlledConsoleFailure =
    input.context.phase === "fault_injection" &&
    input.event === "console_error" &&
    category === "connection_refused" &&
    input.correlatedFault === true;
  const phase =
    input.context.phase === "fault_injection" &&
    !controlledNetworkFailure &&
    !controlledConsoleFailure
      ? "product"
      : input.context.phase;
  return {
    event: input.event,
    component:
      input.event === "console_error"
        ? "browser_console"
        : input.event === "page_error"
          ? "browser_page"
          : "network",
    endpoint:
      isNetwork && input.rawUrl
        ? sanitizedEndpoint(input.rawUrl, input.method ?? "REQUEST")
        : null,
    status:
      typeof input.status === "number" && Number.isInteger(input.status)
        ? input.status
        : null,
    category,
    check: input.context.check,
    phase,
  };
}

export function productFailedRequestsForCheck(
  details: BrowserSafetyDetail[],
  check: GuestCheckNumber,
): BrowserSafetyDetail[] {
  return details.filter(
    (detail) =>
      detail.event === "failed_request" &&
      detail.check === check &&
      detail.phase === "product",
  );
}

export function productExecutionSafetyDetails(
  details: BrowserSafetyDetail[],
): BrowserSafetyDetail[] {
  return details.filter((detail) => detail.phase === "product");
}

export function benignLoopbackNavigationAbort(input: {
  rawUrl: string;
  method: string;
  rawError: string;
  isNavigationRequest: boolean;
}): boolean {
  if (
    input.method !== "GET" ||
    !input.rawError.toLowerCase().includes("err_aborted")
  ) {
    return false;
  }
  try {
    const url = new URL(input.rawUrl);
    return (
      ["localhost", "127.0.0.1", "::1"].includes(url.hostname) &&
      url.pathname === "/chat"
    );
  } catch {
    return false;
  }
}

export function expectedMutationDeltasOnly(
  before: Record<string, number>,
  after: Record<string, number>,
  expected: Record<string, number>,
): boolean {
  const routes = new Set([
    ...Object.keys(before),
    ...Object.keys(after),
    ...Object.keys(expected),
  ]);
  return [...routes].every(
    (route) =>
      (after[route] ?? 0) - (before[route] ?? 0) === (expected[route] ?? 0),
  );
}

export class BrowserSafetyMonitor {
  consoleErrors = 0;
  pageErrors = 0;
  failedRequests = 0;
  hostedWrites = 0;
  credentialExposure = 0;
  readonly mutations = new Map<string, number>();
  private readonly details: BrowserSafetyDetail[] = [];
  private readonly requestContexts = new WeakMap<Request, BrowserSafetyContext>();

  constructor(
    private readonly context: () => BrowserSafetyContext = () => ({
      check: null,
      phase: "product",
    }),
  ) {}

  attach(page: Page): void {
    page.on("console", (message) => {
      if (message.type() === "error") {
        const context = this.context();
        const previous = this.details.at(-1);
        this.consoleErrors += 1;
        this.details.push(
          browserSafetyDetail({
            event: "console_error",
            rawError: message.text(),
            correlatedFault:
              context.phase === "fault_injection" &&
              previous?.event === "failed_request" &&
              previous.phase === "fault_injection" &&
              previous.check === context.check,
            context,
          }),
        );
      }
      this.scan(message.text());
    });
    page.on("pageerror", (error) => {
      this.pageErrors += 1;
      this.details.push(
        browserSafetyDetail({
          event: "page_error",
          rawError: error.message,
          context: this.context(),
        }),
      );
      this.scan(error.message);
    });
    page.on("requestfailed", (request) => {
      if (
        benignLoopbackNavigationAbort({
          rawUrl: request.url(),
          method: request.method(),
          rawError: request.failure()?.errorText ?? "",
          isNavigationRequest: request.isNavigationRequest(),
        })
      ) {
        return;
      }
      this.failedRequests += 1;
      this.details.push(
        browserSafetyDetail({
          event: "failed_request",
          rawUrl: request.url(),
          method: request.method(),
          rawError: request.failure()?.errorText ?? "",
          context: this.requestContexts.get(request) ?? this.context(),
        }),
      );
    });
    page.on("response", (response) => {
      if (response.status() < 400) return;
      this.failedRequests += 1;
      this.details.push(
        browserSafetyDetail({
          event: "failed_request",
          rawUrl: response.url(),
          method: response.request().method(),
          status: response.status(),
          context:
            this.requestContexts.get(response.request()) ?? this.context(),
        }),
      );
    });
    page.on("request", (request) => {
      this.requestContexts.set(request, this.context());
      const url = new URL(request.url());
      const isWrite = !["GET", "HEAD", "OPTIONS"].includes(request.method());
      if (isWrite) {
        const key = sanitizedEndpoint(request.url(), request.method());
        this.mutations.set(key, (this.mutations.get(key) ?? 0) + 1);
        if (!["localhost", "127.0.0.1"].includes(url.hostname)) {
          this.hostedWrites += 1;
        }
      }
      if (!["localhost", "127.0.0.1"].includes(url.hostname)) {
        const headers = request.headers();
        const sensitiveShape = [
          url.search,
          Object.keys(headers).join(" "),
          request.postData() ?? "",
        ].join(" ");
        if (
          /token|cookie|authorization|bearer|password|email|session|secret/i.test(
            sensitiveShape,
          )
        ) {
          this.credentialExposure += 1;
        }
      }
    });
  }

  private scan(value: string): void {
    if (
      JWT_PATTERN.test(value) ||
      EMAIL_PATTERN.test(value) ||
      /refresh[_ -]?token|service[_ -]?role|authorization:\s*bearer/i.test(
        value,
      )
    ) {
      this.credentialExposure += 1;
    }
    JWT_PATTERN.lastIndex = 0;
    EMAIL_PATTERN.lastIndex = 0;
  }

  mutationSnapshot(): Record<string, number> {
    return Object.fromEntries([...this.mutations.entries()].sort());
  }

  detailSnapshot(): BrowserSafetyDetail[] {
    return this.details.map((detail) => ({ ...detail }));
  }
}

function evidenceDirectory(): string {
  const segment =
    process.env.ARGUS_GUEST_QA_EVIDENCE_SEGMENT?.trim() || "authoritative";
  if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(segment)) {
    throw new Error("Guest QA evidence segment is invalid");
  }
  const directory = path.join(
    REPOSITORY_ROOT,
    "temp",
    "qa-evidence-guest",
    requireCandidateSha(),
    segment,
  );
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  chmodSync(directory, 0o700);
  return directory;
}

export async function safeScreenshot(
  page: Page,
  name: string,
  target?: ReturnType<Page["locator"]>,
): Promise<void> {
  if (!/^[a-z0-9-]+$/.test(name)) throw new Error("Unsafe screenshot name");
  const destination = path.join(evidenceDirectory(), `${name}.png`);
  const mask = [
    page.locator('input[type="email"]'),
    page.locator('input[type="password"]'),
    page.locator("textarea"),
    page.locator("[data-conversation-id]"),
  ];
  if (target) {
    await target.screenshot({ path: destination, mask });
  } else {
    await page.screenshot({
      path: destination,
      fullPage: false,
      mask,
    });
  }
  chmodSync(destination, 0o600);
}

export async function safeVisibleProductScreenshot(
  page: Page,
  name: string,
): Promise<string> {
  if (!/^[a-z0-9-]+$/.test(name)) throw new Error("Unsafe screenshot name");
  const visibleText = await page.locator("body").innerText();
  if (
    /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/i.test(
      visibleText,
    ) ||
    /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i.test(visibleText)
  ) {
    throw new Error("Visible product text contains a private identifier");
  }
  const destination = path.join(evidenceDirectory(), `${name}.png`);
  await page.screenshot({
    path: destination,
    fullPage: false,
    mask: [
      page.locator('input[type="email"]'),
      page.locator('input[type="password"]'),
      page.locator("textarea"),
    ],
  });
  chmodSync(destination, 0o600);
  return destination;
}

export function assertSafeEvidence(evidence: SafeEvidence): void {
  const candidate = requireCandidateSha();
  if (evidence.candidate_sha !== candidate) {
    throw new Error("Evidence SHA does not match candidate");
  }
  const labels = [
    ...evidence.owner_labels,
    ...evidence.conversation_labels,
    ...evidence.artifact_labels,
  ];
  if (labels.some((label) => !/^[0-9a-f]{20}$/.test(label))) {
    throw new Error("Evidence contains a non-hashed product identifier");
  }
  const safeEndpoint = /^[A-Z]+ \/[A-Za-z0-9_./:@-]+$/;
  const safeCategories = new Set([
    "connection_refused",
    "connection_reset",
    "aborted",
    "timeout",
    "hydration_error",
    "network_error",
    "console_error",
    "page_error",
    "failed_request",
    "http_client_error",
    "http_server_error",
  ]);
  for (const detail of evidence.browser_safety_details) {
    if (
      (detail.endpoint !== null && !safeEndpoint.test(detail.endpoint)) ||
      !safeCategories.has(detail.category) ||
      (detail.check !== null && (detail.check < 1 || detail.check > 20))
    ) {
      throw new Error("Evidence contains an unsafe browser safety detail");
    }
  }
  if (
    Object.keys(evidence.normalized_mutation_counts).some(
      (endpoint) => !safeEndpoint.test(endpoint),
    )
  ) {
    throw new Error("Evidence contains an unsafe mutation endpoint");
  }
  const serialized = JSON.stringify(evidence);
  if (
    UUID_PATTERN.test(serialized) ||
    JWT_PATTERN.test(serialized) ||
    EMAIL_PATTERN.test(serialized) ||
    serialized.includes("?")
  ) {
    throw new Error("Evidence contains a forbidden identifier or secret shape");
  }
  UUID_PATTERN.lastIndex = 0;
  JWT_PATTERN.lastIndex = 0;
  EMAIL_PATTERN.lastIndex = 0;
}

export function writeEvidence(evidence: SafeEvidence): void {
  assertSafeEvidence(evidence);
  const directory = evidenceDirectory();
  const finalPath = path.join(directory, "summary.json");
  const temporaryPath = path.join(
    directory,
    `.summary-${process.pid}-${Date.now()}.tmp`,
  );
  writeFileSync(temporaryPath, `${JSON.stringify(evidence, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx",
  });
  chmodSync(temporaryPath, 0o600);
  renameSync(temporaryPath, finalPath);
  chmodSync(finalPath, 0o600);
}

function serviceClient(): SupabaseClient {
  const url = localUrl(
    process.env.SUPABASE_PROJECT_URL,
    "SUPABASE_PROJECT_URL",
  ).origin;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!key) throw new Error("Local service role key is required");
  return createClient(url, key, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}

export async function createDisposableRegisteredIdentity(): Promise<DisposableIdentity> {
  const client = serviceClient();
  const email = `guest-qa-${randomBytes(10).toString("hex")}@example.test`;
  const password = `Qa!${randomBytes(24).toString("base64url")}`;
  const { data, error } = await client.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  });
  if (error || !data.user) {
    throw new Error("Could not create the local registered QA identity");
  }
  const userId = data.user.id;
  const { error: profileError } = await client.from("profiles").upsert({
    id: userId,
    email,
    display_name: "Local QA",
    language: "en",
  });
  if (profileError) {
    await client.auth.admin.deleteUser(userId);
    throw new Error("Could not create the local registered QA profile");
  }
  const { error: allowlistError } = await client
    .from("private_alpha_allowlist")
    .upsert({ email });
  if (allowlistError) {
    await client.auth.admin.deleteUser(userId);
    throw new Error("Could not allowlist the local registered QA identity");
  }
  return { userId, email, password };
}

export function newSignupCredentials(): Pick<
  DisposableIdentity,
  "email" | "password"
> {
  return {
    email: `guest-link-${randomBytes(10).toString("hex")}@example.test`,
    password: `Qa!${randomBytes(24).toString("base64url")}`,
  };
}

export async function allowlistDisposableRegisteredIdentity(
  userId: string,
): Promise<void> {
  requireUuid(userId, "disposable registered identity");
  const client = serviceClient();
  const { data: identity, error: identityError } =
    await client.auth.admin.getUserById(userId);
  const email = identity.user?.email;
  if (identityError || !email) {
    throw new Error("Could not inspect the local registered QA identity");
  }
  const { error } = await client
    .from("private_alpha_allowlist")
    .upsert({ email });
  if (error) {
    throw new Error("Could not allowlist the local registered QA identity");
  }
}

export async function deleteDisposableIdentity(userId: string): Promise<void> {
  requireUuid(userId, "disposable identity");
  const client = serviceClient();
  const { data: identity, error: identityError } =
    await client.auth.admin.getUserById(userId);
  if (identityError && !/not found/i.test(identityError.message)) {
    throw new Error("Could not inspect the local disposable identity");
  }
  const email = identity.user?.email;
  if (email) {
    const { error: allowlistError } = await client
      .from("private_alpha_allowlist")
      .delete()
      .eq("email", email);
    if (allowlistError) {
      throw new Error("Could not remove the local disposable allowlist row");
    }
  }
  const { error } = await client.auth.admin.deleteUser(userId);
  if (error && !/not found/i.test(error.message)) {
    throw new Error("Could not delete the local disposable identity");
  }
}

export function purgeDisposableQaEvidence(): void {
  const state = zeroStateSnapshot();
  if (state.auth_users !== 0 || state.profiles !== 0) {
    throw new Error(
      "Guest QA refused to purge evidence before identity cleanup",
    );
  }
  const purged = psqlJson<{ ok: boolean }>(`
    with deleted_cost as (
      delete from public.cost_ledger_entries returning 1
    ),
    deleted_feedback as (
      delete from public.feedback returning 1
    ),
    deleted_receipts as (
      delete from public.route_receipts returning 1
    ),
    deleted_writes as (
      delete from public.checkpoint_writes returning 1
    ),
    deleted_blobs as (
      delete from public.checkpoint_blobs returning 1
    ),
    deleted_checkpoints as (
      delete from public.checkpoints returning 1
    )
    select json_build_object('ok', true)::text
  `);
  if (!purged.ok) {
    throw new Error("Guest QA could not purge disposable local evidence");
  }
}

export function emptyEvidence(): SafeEvidence {
  return {
    candidate_sha: requireCandidateSha(),
    served_sha: requireCandidateSha(),
    frontend_mode: "production",
    status: "failed",
    completed_checks: [],
    failure_check: null,
    flags_restored_false: false,
    fresh_context_verified: false,
    owner_labels: [],
    conversation_labels: [],
    artifact_labels: [],
    check4_initial_confirmation: null,
    check4_refined_confirmation: null,
    simulation_usage_matches: false,
    distinct_uuid_conversion: false,
    new_account_resume_count: 0,
    existing_claim_owner_changed: false,
    existing_claim_duplicate_count: 0,
    existing_claim_resume_count: 0,
    feedback_rows_added: 0,
    feedback_email_present: false,
    feedback_transcript_present: false,
    interrupted_usage_delta: 0,
    cleanup_deleted_count: 0,
    cleanup_permanent_control_preserved: false,
    cleanup_complete_graph_rows_before: 0,
    cleanup_complete_graph_rows_after: 0,
    cleanup_feedback_deleted: false,
    cleanup_usage_deleted: false,
    cleanup_route_retained: false,
    cleanup_cost_retained: false,
    cross_owner_result_count: 0,
    console_error_count: 0,
    page_error_count: 0,
    failed_request_count: 0,
    browser_safety_details: [],
    teardown_console_error_count: 0,
    teardown_page_error_count: 0,
    teardown_failed_request_count: 0,
    teardown_hosted_write_count: 0,
    teardown_credential_exposure_count: 0,
    hosted_write_count: 0,
    server_product_analytics_disabled: false,
    credential_exposure_count: 0,
    provider_cost_usd: 0,
    provider_latency_ms: 0,
    normalized_mutation_counts: {},
    teardown_clean: false,
  };
}
