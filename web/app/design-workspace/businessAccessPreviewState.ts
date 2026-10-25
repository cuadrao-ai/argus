export const accessRoles = ["owner", "admin", "editor", "viewer"] as const;
export type AccessRole = typeof accessRoles[number];
export type PreviewPerson = { email: string; permission: AccessRole; status: "granted" | "pending"; current?: boolean; resendCount?: number };
export type PreviewActor = { email: string; permission: AccessRole };
type HistoryPerson = Omit<PreviewPerson, "status"> & { status: PreviewPerson["status"] | "cancelled" | "revoked" };
type Batch = { history?: HistoryPerson[]; accessFixtureVersion?: number; [key: string]: unknown };
type Draft = { invitationBatch?: Batch; invitation?: HistoryPerson; [key: string]: unknown };
type StorageLike = Pick<Storage, "getItem" | "setItem">;
export type AccessAction = { kind: "role"; email: string; permission: AccessRole } | { kind: "remove" | "cancel" | "resend"; email: string };
export type AccessGuard = "owner_only" | "self" | "last_owner" | "missing" | null;

const emailKey = (email: string) => email.trim().toLowerCase();
export function invitationStorageKeys(businessId: string) {
  const guide = `cuadrao-workspace-guide-actions-v1-business-${encodeURIComponent(businessId)}`;
  return { guide, draft: `${guide}-invite-draft` };
}
function read(storage: StorageLike, key: string): Draft {
  try { return JSON.parse(storage.getItem(key) || "{}"); } catch { return {}; }
}
function validPerson(person: HistoryPerson | undefined): person is HistoryPerson {
  return Boolean(person && typeof person.email === "string" && person.email.trim() && accessRoles.includes(person.permission));
}
export function readAccessPreview(storage: StorageLike, businessId: string, actor: PreviewActor | null) {
  const keys = invitationStorageKeys(businessId);
  const draft = read(storage, keys.draft);
  const guide = read(storage, keys.guide);
  const people = new Map<string, PreviewPerson>();
  for (const person of [guide.invitation, draft.invitation, ...(draft.invitationBatch?.history ?? [])]) {
    if (!validPerson(person)) continue;
    const email = emailKey(person.email);
    if (person.status === "cancelled" || person.status === "revoked") { people.delete(email); continue; }
    const previous = people.get(email);
    if (!previous || person.status === "granted" || previous.status !== "granted") people.set(email, { ...person, email, status: person.status });
  }
  if (actor?.email) people.set(emailKey(actor.email), { ...actor, email: emailKey(actor.email), status: "granted", current: true });
  return { members: [...people.values()].filter(person => person.status === "granted").sort((a, b) => Number(Boolean(b.current)) - Number(Boolean(a.current)) || a.email.localeCompare(b.email)), pending: [...people.values()].filter(person => person.status === "pending").sort((a,b) => a.email.localeCompare(b.email)) };
}

/** Only the named synthetic review business receives these accepted-member fixtures. */
export function seedAccessPreview(storage: StorageLike, businessId: string) {
  if (businessId !== "fixture-space") return false;
  const key = invitationStorageKeys(businessId).draft;
  const draft = read(storage, key);
  const batch: Batch = draft.invitationBatch ?? {recipients: [], nextId: 1, phase: "draft"};
  if (batch.accessFixtureVersion === 1) return false;
  const history = batch.history ?? [];
  const fixtures: HistoryPerson[] = [
    { email: "accountant@example.test", permission: "admin", status: "granted" },
    { email: "assistant@example.test", permission: "editor", status: "granted" },
    { email: "observer@example.test", permission: "viewer", status: "granted" },
  ];
  draft.invitationBatch = { ...batch, accessFixtureVersion: 1, history: [...history, ...fixtures.filter(person => !history.some(existing => emailKey(existing.email) === person.email))] };
  storage.setItem(key, JSON.stringify(draft));
  return true;
}
export function accessActionGuard(snapshot: ReturnType<typeof readAccessPreview>, actor: PreviewActor | null, action: AccessAction): AccessGuard {
  if (!actor || !["owner", "admin"].includes(actor.permission)) return "owner_only";
  const target = [...snapshot.members, ...snapshot.pending].find(person => person.email === emailKey(action.email));
  if (!target) return "missing";
  if ((target.permission === "owner" || (action.kind === "role" && action.permission === "owner")) && actor.permission !== "owner") return "owner_only";
  if (target.status === "granted" && target.permission === "owner" && (action.kind === "remove" || (action.kind === "role" && action.permission !== "owner")) && snapshot.members.filter(person => person.permission === "owner").length <= 1) return "last_owner";
  if (target.status === "granted" && target.email === emailKey(actor.email)) return "self";
  if ((action.kind === "cancel" || action.kind === "resend") && target.status !== "pending") return "missing";
  if (action.kind === "remove" && target.status !== "granted") return "missing";
  return null;
}
export function changeAccessPreview(storage: StorageLike, businessId: string, actor: PreviewActor | null, action: AccessAction): AccessGuard {
  const snapshot = readAccessPreview(storage, businessId, actor);
  const guard = accessActionGuard(snapshot, actor, action);
  if (guard) return guard;
  const target = [...snapshot.members, ...snapshot.pending].find(person => person.email === emailKey(action.email))!;
  const keys = invitationStorageKeys(businessId), draft = read(storage, keys.draft);
  const batch: Batch = draft.invitationBatch ?? {recipients: [], nextId: 1, phase: "draft"};
  const updated: HistoryPerson = action.kind === "role" ? { ...target, permission: action.permission }
    : action.kind === "resend" ? { ...target, status: "pending", resendCount: (target.resendCount ?? 0) + 1 }
    : { ...target, status: action.kind === "cancel" ? "cancelled" : "revoked" };
  draft.invitationBatch = { ...batch, history: [...(batch.history ?? []).filter(person => emailKey(person.email) !== target.email), updated] };
  storage.setItem(keys.draft, JSON.stringify(draft));
  return null;
}
