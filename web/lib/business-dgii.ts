import { apiFetch } from "./argus-api-transport";
import { readBusinessDossier, type BusinessDossier } from "./business-dossier";

export type DgiiDeclaration = Record<string, string | boolean | null> & { form: "606" | "607" };
export type DgiiReview = {
  fiscal: { rnc: string | null; ncf: string | null; itbis: string | null };
  declaration: DgiiDeclaration;
};
export type DgiiField = { name: string; label: string; kind: "select" | "date" | "text" | "money"; options: string[]; /** The label of each option that has one, by code. */ labels?: Record<string, string> };
export type DgiiFields = Record<"606" | "607", DgiiField[]>;
/** The 606 answers a person gives one by one. An absent field stays as it was. */
export type PurchaseChoice = { category?: string | null; payment_method?: string | null };
export type TaxIdType = "rnc" | "cedula";
export type TaxId = { type: TaxIdType; value: string };
/** The razón social a person who manages the Business confirmed against the registry row for its tax id. */
export type LegalName = { value: string; confirmed_at: string };
export type FiscalProfile = { name: string | null; tax_id: TaxId | null; legal_name: LegalName | null; can_edit: boolean };
export type FiscalProfileInput = {
  name: string;
  previous_name: string | null;
  tax_id: TaxId | null;
  previous_tax_id: TaxId | null;
};

/** What the DGII registry says of one tax id, in the words a counterparty's RNC gets. */
export type RegistryRecord = { rnc: string; name: string; trade_name: string | null; status: string; file_date: string | null };
export type RegistryAnswer = { tax_id: TaxId; verification: "verificado" | "no_activo" | "sin_verificar"; record: RegistryRecord | null; checked_at: string };
export type LegalNameInput = { legal_name: string | null; previous_legal_name: string | null; tax_id: TaxId; confirmed: boolean };

export const getDgiiFields = (): Promise<DgiiFields> => apiFetch("/business/fiscal-profile/fields");
export const getFiscalProfile = (draftId?: string): Promise<FiscalProfile> => apiFetch(`/business/fiscal-profile${draftId ? `?draft_id=${encodeURIComponent(draftId)}` : ""}`);
export const setFiscalProfile = (input: FiscalProfileInput, key: string): Promise<FiscalProfile> => apiFetch("/business/fiscal-profile", { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify(input) });
export const lookupRegistry = (taxId: TaxId, signal?: AbortSignal): Promise<RegistryAnswer> => apiFetch("/business/fiscal-profile/registry", { method: "POST", body: JSON.stringify({ tax_id: taxId }), signal });
export const setLegalName = (input: LegalNameInput, key: string): Promise<FiscalProfile> => apiFetch("/business/fiscal-profile/legal-name", { method: "PUT", headers: { "Idempotency-Key": key }, body: JSON.stringify(input) });
export const reviewDgii = (draftId: string, version: number, dgii: DgiiReview, key: string): Promise<BusinessDossier> => apiFetch<unknown>(`/business/drafts/${encodeURIComponent(draftId)}/review`, { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify({ version, dgii }) }).then(readBusinessDossier);
export const reviewPurchase = (draftId: string, version: number, purchase: PurchaseChoice, key: string): Promise<BusinessDossier> => apiFetch<unknown>(`/business/drafts/${encodeURIComponent(draftId)}/review`, { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify({ version, purchase }) }).then(readBusinessDossier);
