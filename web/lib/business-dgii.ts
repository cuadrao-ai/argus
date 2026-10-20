import { apiFetch } from "./argus-api-transport";
import type { BusinessDossier } from "./business-dossier";

export type DgiiDeclaration = Record<string, string | boolean | null> & { form: "606" | "607" };
export type DgiiReview = {
  fiscal: { rnc: string | null; ncf: string | null; itbis: string | null };
  declaration: DgiiDeclaration;
};
export type DgiiField = { name: string; label: string; kind: "select" | "date" | "text" | "money"; options: string[] };
export type DgiiFields = Record<"606" | "607", DgiiField[]>;
export type FiscalProfile = { rnc: string | null; can_edit: boolean };

export const getDgiiFields = (): Promise<DgiiFields> => apiFetch("/business/fiscal-profile/fields");
export const getFiscalProfile = (draftId?: string): Promise<FiscalProfile> => apiFetch(`/business/fiscal-profile${draftId ? `?draft_id=${encodeURIComponent(draftId)}` : ""}`);
export const setFiscalProfile = (rnc: string | null, previousRnc: string | null, key: string): Promise<FiscalProfile> => apiFetch("/business/fiscal-profile", { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify({ rnc, previous_rnc: previousRnc }) });
export const reviewDgii = (draftId: string, version: number, dgii: DgiiReview, key: string): Promise<BusinessDossier> => apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/review`, { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify({ version, dgii }) });
export const approveFiscalRecord = (draftId: string, version: number, action: "record_income" | "record_refund", key: string): Promise<BusinessDossier> => apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/approve`, { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ version, action }) });
