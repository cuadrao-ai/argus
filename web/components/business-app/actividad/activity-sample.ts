// Actividad's sample: the feed's shape (GET /business/activity, #1407), the fields the design still needs on top of
// it, and the invented rows the local preview and its search show.

import type { BusinessActivityActor, BusinessActivityItem } from "@/lib/business-activity-api";
import { dossierFixtureIds } from "../dossier-fixtures";

/* ---------- Contract shape: GET /business/activity (PR #1407) ---------- */

export type ActorKind = "member" | "owner_via_agent" | "extractor";
export type LedgerAction =
  | "delete_document" | "restore_document" | "purge_document" | "expire_document" | "review_draft" | "approve_expense" | "approve_income" | "approve_refund" | "reopen_draft" | "capture_note" | "prepare_attachment"
  | "rebind_attachment" | "settle_remainder" | "mark_personal" | "decide_606" | "resolve_duplicate" | "edit_current_note"
  | "append_supporting_file" | "receipt_upload" | "receipt_review" | "receipt_confirm" | "business_ask"
  | "set_business_rnc" | "set_business_legal_name" | "business_propose_activity" | "business_attach_source" | "business_propose_allocation"
  | "owner_grant" | "grant_access" | "invite_access" | "accept_invite" | "revoke_grant" | "revoke_invite" | "change_role" | "other";
export type ActivityItem = {
  id: string;
  occurred_at: string;
  actor: BusinessActivityActor;
  action: LedgerAction;
  object: { kind: "draft" | "receipt" | "grant" | "invite"; id: string; label?: string; purged?: boolean } | null;
};

/* ---------- MISSING from #1407: what this design needs on top ---------- */

/** Events the design shows that the ledger feed does not carry yet. */
/** ACT-2b brings these; no live rows until then. */
export type MissingAction = "invoice_draft_created" | "invoice_revision_saved" | "document_read" | "document_read_failed" | "receipt_reading_enabled" | "receipt_reading_disabled" | "ownership_transferred";
export type DraftItem = Omit<ActivityItem, "action" | "actor" | "object"> & {
  action: LedgerAction | MissingAction;
  /** null = an older event with no recorded actor (MISSING: nullable actor). MISSING: `membership`, so a member who left keeps their name. */
  actor: (ActivityItem["actor"] & { membership?: "current" | "former" }) | null;
  object: { kind: "draft" | "receipt" | "grant" | "invite" | "invoice"; id: string; label?: string; purged?: boolean } | null;
  /** MISSING: a readable name for the affected record, and a short detail such as a role. */
  missing?: { object_label?: string; detail?: string; personal?: boolean };
};

/* ---------- Fixtures, relative to now so the draft always reads fresh ---------- */

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
const DAY = 24 * 60;
const LUCIA = { display_name: "Lucía Peña", shown_as: "name" as const, kind: "member" as const };
const CARLOS = { display_name: "Carlos Méndez", shown_as: "name" as const, kind: "member" as const };
const READER = { display_name: null, shown_as: null, kind: "extractor" as const };
const draft = (key: keyof typeof dossierFixtureIds) => ({ kind: "draft" as const, id: dossierFixtureIds[key] });

export function fixtureItems(): DraftItem[] {
  // Newest first, as the feed returns them.
  return ([] as DraftItem[]).concat([
    { id: "a01", occurred_at: minutesAgo(12), actor: LUCIA, action: "approve_expense", object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a02", occurred_at: minutesAgo(26), actor: READER, action: "document_read", object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a03", occurred_at: minutesAgo(27), actor: CARLOS, action: "receipt_upload", object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a04", occurred_at: minutesAgo(95), actor: READER, action: "document_read_failed", object: draft("unknown"), missing: { object_label: "Foto de recibo, 10:51" } },
    { id: "a05", occurred_at: minutesAgo(140), actor: { ...LUCIA, kind: "owner_via_agent" }, action: "capture_note", object: draft("unprepared"), missing: { object_label: "Almuerzo con cliente" } },
    { id: "a06", occurred_at: minutesAgo(210), actor: CARLOS, action: "invoice_draft_created", object: { kind: "invoice", id: "inv-0042" }, missing: { object_label: "Factura a Hotel Costa Azul" } },
    { id: "a07", occurred_at: minutesAgo(DAY + 60), actor: LUCIA, action: "change_role", object: { kind: "grant", id: "g-carlos" }, missing: { object_label: "Carlos Méndez", detail: "Editor" } },
    { id: "a08", occurred_at: minutesAgo(DAY + 120), actor: CARLOS, action: "append_supporting_file", object: draft("income"), missing: { object_label: "Cliente Taller Rodríguez" } },
    { id: "a09", occurred_at: minutesAgo(DAY + 185), actor: LUCIA, action: "approve_income", object: draft("income"), missing: { object_label: "Cliente Taller Rodríguez" } },
    { id: "a10", occurred_at: minutesAgo(DAY + 300), actor: CARLOS, action: "resolve_duplicate", object: draft("fiscal"), missing: { object_label: "Estación Ruta 3" } },
    { id: "a11", occurred_at: minutesAgo(2 * DAY + 90), actor: CARLOS, action: "accept_invite", object: { kind: "invite", id: "i-carlos" }, missing: { object_label: "Carlos Méndez" } },
    { id: "a12", occurred_at: minutesAgo(3 * DAY + 30), actor: LUCIA, action: "invite_access", object: { kind: "invite", id: "i-carlos" }, missing: { object_label: "Carlos Méndez", detail: "Editor" } },
    { id: "a13", occurred_at: minutesAgo(3 * DAY + 50), actor: LUCIA, action: "set_business_rnc", object: null },
    { id: "a14", occurred_at: minutesAgo(3 * DAY + 400), actor: { display_name: "Ana Rosario", shown_as: "name", kind: "member", membership: "former" }, action: "edit_current_note", object: draft("fiscal"), missing: { object_label: "Estación Ruta 3" } },
    { id: "a15", occurred_at: minutesAgo(5 * DAY + 20), actor: LUCIA, action: "mark_personal", object: draft("unknownKind"), missing: { object_label: "Supermercado Nacional", personal: true } },
    { id: "a19", occurred_at: minutesAgo(4 * DAY + 10), actor: LUCIA, action: "receipt_reading_enabled", object: null },
    { id: "a21", occurred_at: minutesAgo(7 * DAY + 15), actor: LUCIA, action: "ownership_transferred", object: null },
    { id: "a22", occurred_at: minutesAgo(8 * DAY + 40), actor: LUCIA, action: "receipt_reading_disabled", object: null },
    { id: "a20", occurred_at: minutesAgo(6 * DAY + 45), actor: { display_name: null, shown_as: "former", kind: "member", membership: "former" }, action: "receipt_upload", object: draft("stale"), missing: { object_label: "Colmado El Progreso" } },
    { id: "a16", occurred_at: minutesAgo(5 * DAY + 70), actor: CARLOS, action: "invoice_revision_saved", object: { kind: "invoice", id: "inv-0041" }, missing: { object_label: "Factura a Colmado Peña" } },
    { id: "a17", occurred_at: minutesAgo(9 * DAY), actor: null, action: "receipt_upload", object: draft("readOnly"), missing: { object_label: "Nube Hosting" } },
    { id: "a18", occurred_at: minutesAgo(9 * DAY + 30), actor: LUCIA, action: "decide_606", object: draft("readOnly"), missing: { object_label: "Nube Hosting" } },
  ]).sort((a, z) => z.occurred_at.localeCompare(a.occurred_at));
}

const MISSING_ACTIONS = new Set<string>(["invoice_draft_created", "invoice_revision_saved", "document_read", "document_read_failed", "receipt_reading_enabled", "receipt_reading_disabled", "ownership_transferred"]);
/** `?activity=contract` shows only what #1407 returns today: no labels, no events it does not carry. */
export const toContract = (items: DraftItem[]) => items.filter((item) => !MISSING_ACTIONS.has(item.action) && item.actor).map((item) => ({ ...item, actor: item.actor && contractActor(item.actor), missing: undefined }));

/** A sample actor as the feed answers it, without the fields the design adds. */
function contractActor(actor: NonNullable<DraftItem["actor"]>): BusinessActivityActor {
  const contract = { ...actor };
  delete contract.membership;
  return contract;
}

/** The sample's rows as the feed answers them, each named record as its label, for the sample's search. */
export const sampleActivityFeed = (): BusinessActivityItem[] =>
  fixtureItems().flatMap((item) => {
    if (MISSING_ACTIONS.has(item.action) || item.object?.kind === "invoice") return [];
    const object = item.object ? { ...item.object, label: item.missing?.object_label } as BusinessActivityItem["object"] : null;
    return [{ id: item.id, occurred_at: item.occurred_at, actor: item.actor && contractActor(item.actor), action: item.action, object }];
  });
