// DRAFT (design lane): Inicio overview preview data. Each value is shaped like the response that owns it.
// Real and wired today: receipt counts and Bandeja rows come from the workspace records (GET /business/receipt-activity, the Bandeja page).
// MISSING on the server: `RECENT_WORK` (no recents endpoint). Setup progress is the server's (GET /business/setup).

import { dossierFixtureIds } from "../dossier-fixtures";

/** GET /business/invoices → stage_counts, all dates. */
export const INVOICE_STAGE_COUNTS: Record<string, number> = { draft: 2, issued: 5, processing: 0 };

/** MISSING: `GET /business/recents` → records and drafts this person opened or edited, newest first, only ones they can still open. */
export type RecentWork = { id: string; kind: "invoice_draft" | "record" | "receipt"; label: string; edited_at: string; target: { kind: "draft"; id: string } | { kind: "invoicing" } };
const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3_600_000).toISOString();
export const RECENT_WORK: RecentWork[] = [
  { id: "r1", kind: "invoice_draft", label: "Factura a Taller Brisa", edited_at: hoursAgo(1), target: { kind: "invoicing" } },
  { id: "r2", kind: "record", label: "Ferretería La Esquina", edited_at: hoursAgo(3), target: { kind: "draft", id: dossierFixtureIds.ready } },
  { id: "r3", kind: "record", label: "Cliente Taller Rodríguez", edited_at: hoursAgo(26), target: { kind: "draft", id: dossierFixtureIds.income } },
  { id: "r4", kind: "receipt", label: "Estación Ruta 3", edited_at: hoursAgo(50), target: { kind: "draft", id: dossierFixtureIds.fiscal } },
];
