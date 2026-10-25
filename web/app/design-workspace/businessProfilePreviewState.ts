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

export const providedDetailFields = ["address", "province", "municipality", "email", "phone", "website", "description"] as const;
export type ProvidedDetailField = typeof providedDetailFields[number];
export type BusinessProvidedDetails = Record<ProvidedDetailField, string>;
export type DetailError = "email" | "website" | "length";
export const providedDetailLimits: Record<ProvidedDetailField, number> = {address:200,province:80,municipality:80,email:254,phone:40,website:2048,description:280};
export function normalizeBusinessProvidedDetails(value: unknown): BusinessProvidedDetails {
  const input = object(value);
  const details = Object.fromEntries(providedDetailFields.map(field => [field,text(input[field])])) as BusinessProvidedDetails;
  if(details.website && !/^[a-z][a-z0-9+.-]*:/i.test(details.website)) details.website = `https://${details.website}`;
  return details;
}
export function validateBusinessProvidedDetails(value: BusinessProvidedDetails): Partial<Record<ProvidedDetailField,DetailError>> {
  const errors: Partial<Record<ProvidedDetailField,DetailError>> = {};
  for(const field of providedDetailFields) if(value[field].length > providedDetailLimits[field]) errors[field] = "length";
  if(value.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.email)) errors.email = "email";
  if(value.website) {
    try { const url = new URL(value.website); if(!["http:","https:"].includes(url.protocol) || !url.hostname.includes(".") || /\s/.test(value.website) || url.username || url.password) errors.website = "website"; }
    catch { errors.website = "website"; }
  }
  return errors;
}
export function saveBusinessProvidedDetails(storage: StorageLike,businessId:string,input:BusinessProvidedDetails): BusinessProvidedDetails {
  const details = normalizeBusinessProvidedDetails(input);
  if(Object.keys(validateBusinessProvidedDetails(details)).length) throw new Error("invalid_business_details");
  const saved = read(storage,businessId);
  saved.businessProvidedDetails = details;
  storage.setItem(invitationStorageKeys(businessId).guide,JSON.stringify(saved));
  return details;
}
export type ProfileChecklistKey = "name" | "taxId" | "legalName" | "country" | "address" | "email" | "phone" | "website" | "description";
export type ProfileChecklistItem = {key:ProfileChecklistKey;complete:boolean;section:"basic"|"additional"};
function profileChecklist(profile:{name:string;country:string|null;taxId:TaxId|null;legalName:string|null},details:BusinessProvidedDetails):ProfileChecklistItem[] {
  const errors = validateBusinessProvidedDetails(details);
  const validTaxId = profile.taxId && new RegExp(`^\\d{${profile.taxId.type === "rnc" ? 9 : 11}}$`).test(profile.taxId.value) && !/^0+$/.test(profile.taxId.value);
  return [
    {key:"name",complete:Boolean(profile.name),section:"basic"},
    {key:"taxId",complete:Boolean(validTaxId),section:"basic"},
    {key:"legalName",complete:Boolean(profile.legalName),section:"basic"},
    {key:"country",complete:Boolean(profile.country),section:"basic"},
    {key:"address",complete:Boolean(details.address)&&!errors.address,section:"basic"},
    ...(["email","phone","website","description"] as const).map(key=>({key,complete:Boolean(details[key])&&!errors[key],section:"additional" as const})),
  ];
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
  const providedDetails = normalizeBusinessProvidedDetails(saved.businessProvidedDetails);
  const identity = {name:text(name) || text(workspace.name),country:text(country) || text(workspace.country) || null,taxId,legalName};
  return {...identity,providedDetails,checklist:profileChecklist(identity,providedDetails),invoice:{status,path,action:status === "active" || status === "awaiting-verification" ? "view" : path ? "continue" : "configure"}};
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
