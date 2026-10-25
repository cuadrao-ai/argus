import type { FiscalProfileInput, TaxId } from "@/lib/business-dgii";
import { invitationStorageKeys } from "./businessAccessPreviewState";

type StorageLike = Pick<Storage, "getItem" | "setItem">;
type Saved = Record<string, unknown>;
export const invoiceStatuses = ["not-started", "in-progress", "needs-information", "awaiting-verification", "active"] as const;
export type ProfileInvoiceStatus = typeof invoiceStatuses[number];
const object = (value: unknown): Saved => value && typeof value === "object" && !Array.isArray(value) ? value as Saved : {};
const text = (value: unknown) => typeof value === "string" ? value.trim() : "";
const digits = (value: unknown) => text(value).replace(/[ -]/g, "");
function read(storage: StorageLike, businessId: string): Saved {
  try { return object(JSON.parse(storage.getItem(invitationStorageKeys(businessId).guide) || "{}")); } catch { return {}; }
}

export function readBusinessProfilePreview(storage: StorageLike, businessId: string, name: string, country?: string | null) {
  const saved = read(storage, businessId);
  const workspace = object(saved.workspace), details = object(saved.businessDetails), activation = object(saved.activation);
  const cedula = object(saved.profileTaxId);
  const rnc = digits(details.enteredRnc);
  const taxId: TaxId | null = cedula.type === "cedula" && digits(cedula.value) ? {type:"cedula",value:digits(cedula.value)} : rnc ? {type:"rnc",value:rnc} : null;
  const lookup = object(saved.registryResult);
  const result = lookup.status === "match" && text(lookup.confirmedAt) ? lookup : details.lookupStatus === "match" && text(details.confirmedAt) ? {status:"match",confirmedAt:details.confirmedAt,queriedRnc:details.enteredRnc,record:details.registryRecord} : {};
  const record = object(result.record);
  const legalName = (saved.taxnumber === undefined || digits(saved.taxnumber) === taxId?.value) && taxId?.type === "rnc" && digits(result.queriedRnc) === taxId.value && digits(record.rnc) === taxId.value ? text(record.legalName) || null : null;
  let status: ProfileInvoiceStatus = invoiceStatuses.includes(activation.status as ProfileInvoiceStatus) ? activation.status as ProfileInvoiceStatus : "not-started";
  if(status === "awaiting-verification" && (!text(details.enteredRnc) || !text(details.legalName))) status = "needs-information";
  const path = activation.path === "existing" || activation.path === "new" ? activation.path : null;
  return { name:text(name) || text(workspace.name), country:text(country) || text(workspace.country) || null, taxId, legalName, invoice:{status,path,action:status === "active" || status === "awaiting-verification" ? "view" : path ? "continue" : "configure"} };
}

export function saveBusinessProfilePreview(storage: StorageLike, businessId: string, input: FiscalProfileInput) {
  const saved = read(storage, businessId), details = object(saved.businessDetails);
  const rnc = input.tax_id?.type === "rnc" ? digits(input.tax_id.value) : "";
  const changedRnc = digits(details.enteredRnc) !== rnc;
  saved.workspace = {...object(saved.workspace),name:input.name};
  saved.businessDetails = {...details,enteredRnc:rnc,...(changedRnc ? {legalName:"",registryRecord:null,lookupStatus:"not-checked",confirmedAt:null,checkedAt:null} : {})};
  saved.taxnumber = rnc;
  if(changedRnc) { saved.registryResult = null; saved.legalname = ""; }
  if(input.tax_id?.type === "cedula") saved.profileTaxId = {...input.tax_id,value:digits(input.tax_id.value)};
  else delete saved.profileTaxId;
  storage.setItem(invitationStorageKeys(businessId).guide, JSON.stringify(saved));
}
