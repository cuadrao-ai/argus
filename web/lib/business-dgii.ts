import { apiFetch } from "./argus-api-transport";
import type { BusinessDossier } from "./business-dossier";

export type DgiiDeclaration = Record<string, string | boolean | null> & { form: "606" | "607" };
export type DgiiReview = {
  fiscal: { rnc: string | null; ncf: string | null; itbis: string | null };
  declaration: DgiiDeclaration;
};
export type DgiiField = { name: string; label: string; kind: "select" | "date" | "text" | "money"; options: string[] };
export type DgiiFields = Record<"606" | "607", DgiiField[]>;
export type TaxIdType = "rnc" | "cedula";
export type TaxId = { type: TaxIdType; value: string };
export type FiscalProfile = { name: string; tax_id: TaxId | null; can_edit: boolean };
export type FiscalProfileInput = {
  name: string;
  previous_name: string;
  tax_id: TaxId | null;
  previous_tax_id: TaxId | null;
};

export const getDgiiFields = (): Promise<DgiiFields> => apiFetch("/business/fiscal-profile/fields");
export const getFiscalProfile = (draftId?: string): Promise<FiscalProfile> => apiFetch(`/business/fiscal-profile${draftId ? `?draft_id=${encodeURIComponent(draftId)}` : ""}`);
export const setFiscalProfile = (input: FiscalProfileInput, key: string): Promise<FiscalProfile> => apiFetch("/business/fiscal-profile", { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify(input) });
export const reviewDgii = (draftId: string, version: number, dgii: DgiiReview, key: string): Promise<BusinessDossier> => apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/review`, { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify({ version, dgii }) });
