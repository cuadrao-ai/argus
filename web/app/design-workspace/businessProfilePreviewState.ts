import type { FiscalProfileInput, RegistryAnswer, TaxId } from "@/lib/business-dgii";
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
export const providedDetailLimits: Record<ProvidedDetailField, number> = {address:200,province:80,municipality:80,email:254,phone:40,website:2048,description:280};
export function normalizeBusinessProvidedDetails(value: unknown): BusinessProvidedDetails {
  const input = object(value);
  return Object.fromEntries(providedDetailFields.map(field => [field,text(input[field])])) as BusinessProvidedDetails;
}
/** The local preview has no server, so it has no format rules: it keeps what was typed. */
export function saveBusinessProvidedDetails(storage: StorageLike,businessId:string,input:BusinessProvidedDetails): BusinessProvidedDetails {
  const details = normalizeBusinessProvidedDetails(input);
  const saved = read(storage,businessId);
  saved.businessProvidedDetails = details;
  storage.setItem(invitationStorageKeys(businessId).guide,JSON.stringify(saved));
  return details;
}
export type ProfileChecklistKey = "name" | "taxId" | "legalName" | "country" | "address" | "email" | "phone" | "website" | "description";
export type ProfileChecklistItem = {key:ProfileChecklistKey;complete:boolean;section:"basic"|"additional"};
export function profileChecklist(profile:{name:string;country:string|null;taxId:TaxId|null;legalName:string|null},details:BusinessProvidedDetails,registry:RegistryAnswer|null=null):ProfileChecklistItem[] {
  const validTaxId = profile.taxId && new RegExp(`^\\d{${profile.taxId.type === "rnc" ? 9 : 11}}$`).test(profile.taxId.value) && !/^0+$/.test(profile.taxId.value);
  return [
    {key:"name",complete:Boolean(profile.name),section:"basic"},
    {key:"taxId",complete:Boolean(validTaxId),section:"basic"},
    {key:"legalName",complete:Boolean(profile.legalName)||registry?.record===null,section:"basic"},
    {key:"country",complete:Boolean(profile.country),section:"basic"},
    {key:"address",complete:Boolean(details.address),section:"basic"},
    ...(["email","phone","website","description"] as const).map(key=>({key,complete:Boolean(details[key]),section:"additional" as const})),
  ];
}

export function readBusinessProfilePreview(storage: StorageLike, businessId: string, name: string, country?: string | null) {
  const saved = read(storage, businessId);
  const workspace = object(saved.workspace), details = object(saved.businessDetails), activation = object(saved.activation);
  const cedula = object(saved.profileTaxId);
  const rnc = digits(details.enteredRnc);
  const taxId: TaxId | null = cedula.type === "cedula" && digits(cedula.value) ? {type:"cedula",value:digits(cedula.value)} : rnc ? {type:"rnc",value:rnc} : null;
  let status: ProfileInvoiceStatus = invoiceStatuses.includes(activation.status as ProfileInvoiceStatus) ? activation.status as ProfileInvoiceStatus : "not-started";
  if(status === "awaiting-verification" && (!text(details.enteredRnc) || !text(details.legalName))) status = "needs-information";
  const path = activation.path === "existing" || activation.path === "new" ? activation.path : null;
  const providedDetails = normalizeBusinessProvidedDetails(saved.businessProvidedDetails);
  // The legal name is the server fiscal profile's alone; browser storage never supplies one.
  const identity = {name:text(name) || text(workspace.name),country:text(country) || text(workspace.country) || null,taxId,legalName:null as string|null};
  return {...identity,providedDetails,checklist:profileChecklist(identity,providedDetails),invoice:{status,path,action:status === "active" || status === "awaiting-verification" ? "view" : path ? "continue" : "configure"}};
}

/** Only the named synthetic review business starts with saved values, so a row shows both states. */
export function seedProfilePreview(storage: StorageLike, businessId: string) {
  if(businessId !== "fixture-space") return false;
  const saved = read(storage, businessId);
  if(saved.profileFixtureVersion === 1) return false;
  saved.profileFixtureVersion = 1;
  saved.businessDetails = {...object(saved.businessDetails),enteredRnc:"131245678"};
  saved.businessProvidedDetails = normalizeBusinessProvidedDetails({address:"Calle El Conde 101",province:"Distrito Nacional",municipality:"Santo Domingo",phone:"+1 809 555 0142"});
  storage.setItem(invitationStorageKeys(businessId).guide, JSON.stringify(saved));
  return true;
}

export function saveBusinessProfilePreview(storage: StorageLike, businessId: string, input: FiscalProfileInput) {
  const saved = read(storage, businessId), details = object(saved.businessDetails);
  const rnc = input.tax_id?.type === "rnc" ? digits(input.tax_id.value) : "";
  saved.workspace = {...object(saved.workspace),name:input.name};
  saved.businessDetails = {...details,enteredRnc:rnc};
  saved.taxnumber = rnc;
  if(input.tax_id?.type === "cedula") saved.profileTaxId = {...input.tax_id,value:digits(input.tax_id.value)};
  else delete saved.profileTaxId;
  storage.setItem(invitationStorageKeys(businessId).guide, JSON.stringify(saved));
}
