// Actividad's sample: the feed's shape (GET /business/activity, #1407), the fields the design still needs on top of
// it, and the invented rows the local preview and its search show.

import type { BusinessActivityActor, BusinessActivityItem } from "@/lib/business-activity-api";
import { dossierFixtureIds } from "../dossier-fixtures";

export type DraftItem = Omit<BusinessActivityItem, "actor" | "object"> & {
  actor: (BusinessActivityActor & { membership?: "current" | "former" }) | null;
  object: BusinessActivityItem["object"] | { kind: "invoice"; id: string; label?: string; purged?: boolean };
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
    { id: "a01", occurred_at: minutesAgo(12), actor: LUCIA, action: "approve_expense", area: "records", group: "approvals", restricted: false, object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a02", occurred_at: minutesAgo(26), actor: READER, action: "document_read", area: "documents", group: "reading", restricted: false, object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a03", occurred_at: minutesAgo(27), actor: CARLOS, action: "receipt_upload", area: "documents", group: "uploads", restricted: false, object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a04", occurred_at: minutesAgo(95), actor: READER, action: "document_read_failed", area: "documents", group: "reading", restricted: false, object: draft("unknown"), missing: { object_label: "Foto de recibo, 10:51" } },
    { id: "a05", occurred_at: minutesAgo(140), actor: { ...LUCIA, kind: "owner_via_agent" }, action: "capture_note", area: "records", group: "edits", restricted: false, object: draft("unprepared"), missing: { object_label: "Almuerzo con cliente" } },
    { id: "a06", occurred_at: minutesAgo(210), actor: CARLOS, action: "invoice_draft_created", area: "invoicing", group: "invoices", restricted: false, object: { kind: "invoice", id: "inv-0042" }, missing: { object_label: "Factura a Hotel Costa Azul" } },
    { id: "a07", occurred_at: minutesAgo(DAY + 60), actor: LUCIA, action: "change_role", area: "business", group: "access", restricted: true, object: { kind: "grant", id: "g-carlos" }, missing: { object_label: "Carlos Méndez", detail: "Editor" } },
    { id: "a08", occurred_at: minutesAgo(DAY + 120), actor: CARLOS, action: "append_supporting_file", area: "documents", group: "files", restricted: false, object: draft("income"), missing: { object_label: "Cliente Taller Rodríguez" } },
    { id: "a09", occurred_at: minutesAgo(DAY + 185), actor: LUCIA, action: "approve_income", area: "records", group: "approvals", restricted: false, object: draft("income"), missing: { object_label: "Cliente Taller Rodríguez" } },
    { id: "a10", occurred_at: minutesAgo(DAY + 300), actor: CARLOS, action: "resolve_duplicate", area: "documents", group: "reviews", restricted: false, object: draft("fiscal"), missing: { object_label: "Estación Ruta 3" } },
    { id: "a11", occurred_at: minutesAgo(2 * DAY + 90), actor: CARLOS, action: "accept_invite", area: "business", group: "access", restricted: true, object: { kind: "invite", id: "i-carlos" }, missing: { object_label: "Carlos Méndez" } },
    { id: "a12", occurred_at: minutesAgo(3 * DAY + 30), actor: LUCIA, action: "invite_access", area: "business", group: "access", restricted: true, object: { kind: "invite", id: "i-carlos" }, missing: { object_label: "Carlos Méndez", detail: "Editor" } },
    { id: "a13", occurred_at: minutesAgo(3 * DAY + 50), actor: LUCIA, action: "set_business_rnc", area: "business", group: "settings", restricted: true, object: null },
    { id: "a14", occurred_at: minutesAgo(3 * DAY + 400), actor: { display_name: "Ana Rosario", shown_as: "name", kind: "member", membership: "former" }, action: "edit_current_note", area: "records", group: "edits", restricted: false, object: draft("fiscal"), missing: { object_label: "Estación Ruta 3" } },
    { id: "a15", occurred_at: minutesAgo(5 * DAY + 20), actor: LUCIA, action: "mark_personal", area: "records", group: "edits", restricted: false, object: draft("unknownKind"), missing: { object_label: "Supermercado Nacional", personal: true } },
    { id: "a19", occurred_at: minutesAgo(4 * DAY + 10), actor: LUCIA, action: "receipt_reading_enabled", area: "business", group: "settings", restricted: true, object: null },
    { id: "a21", occurred_at: minutesAgo(7 * DAY + 15), actor: LUCIA, action: "ownership_transferred", area: "business", group: "access", restricted: true, object: null },
    { id: "a22", occurred_at: minutesAgo(8 * DAY + 40), actor: LUCIA, action: "receipt_reading_disabled", area: "business", group: "settings", restricted: true, object: null },
    { id: "a20", occurred_at: minutesAgo(6 * DAY + 45), actor: { display_name: null, shown_as: "former", kind: "member", membership: "former" }, action: "receipt_upload", area: "documents", group: "uploads", restricted: false, object: draft("stale"), missing: { object_label: "Colmado El Progreso" } },
    { id: "a16", occurred_at: minutesAgo(5 * DAY + 70), actor: CARLOS, action: "invoice_revision_saved", area: "invoicing", group: "invoices", restricted: false, object: { kind: "invoice", id: "inv-0041" }, missing: { object_label: "Factura a Colmado Peña" } },
    { id: "a17", occurred_at: minutesAgo(9 * DAY), actor: null, action: "receipt_upload", area: "documents", group: "uploads", restricted: false, object: draft("readOnly"), missing: { object_label: "Nube Hosting" } },
    { id: "a18", occurred_at: minutesAgo(9 * DAY + 30), actor: LUCIA, action: "decide_606", area: "records", group: "approvals", restricted: false, object: draft("readOnly"), missing: { object_label: "Nube Hosting" } },
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
    return [{ id: item.id, occurred_at: item.occurred_at, actor: item.actor && contractActor(item.actor), action: item.action, object, area: item.area, group: item.group, restricted: item.restricted }];
  });
