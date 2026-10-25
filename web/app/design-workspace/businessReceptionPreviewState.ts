import {invitationStorageKeys} from "./businessAccessPreviewState";

const aliasPattern = /^[a-z0-9](?:[a-z0-9-]{1,30})[a-z0-9]$/;

type GuideStorage = Pick<Storage, "getItem" | "setItem" | "key" | "length">;
function read(storage: Pick<Storage,"getItem">, businessId: string): Record<string, unknown> {
  try { const value = JSON.parse(storage.getItem(invitationStorageKeys(businessId).guide) || "{}"); return value && typeof value === "object" && !Array.isArray(value) ? value : {}; } catch { return {}; }
}
export function readReceptionPreview(storage: Pick<Storage,"getItem">, businessId: string) {
  const guide = read(storage,businessId);
  const whatsapp = guide.whatsapp as {linked?: boolean; last4?: string} | undefined;
  return {address: typeof guide.alias === "string" && guide.alias && typeof guide.address === "string" ? guide.address : null, linked: whatsapp?.linked === true, last4: typeof whatsapp?.last4 === "string" ? whatsapp.last4 : null};
}
export function aliasError(storage: GuideStorage, businessId: string, alias: string, domain: string): "required" | "format" | "taken" | "locked" | null {
  if (readReceptionPreview(storage,businessId).address) return "locked";
  if (!alias) return "required";
  if (!aliasPattern.test(alias)) return "format";
  const ownKey = invitationStorageKeys(businessId).guide;
  for(let i=0;i<storage.length;i++) {
    const key = storage.key(i);
    if(!key || key === ownKey || !key.startsWith("cuadrao-workspace-guide-actions-v1-business-")) continue;
    try { if(JSON.parse(storage.getItem(key)||"{}").address === `${alias}@${domain}`) return "taken"; } catch {}
  }
  return null;
}
export function saveReceptionAlias(storage: GuideStorage, businessId: string, alias: string, defaultAddress: string) {
  const domain = defaultAddress.slice(defaultAddress.lastIndexOf("@")+1);
  const error = aliasError(storage,businessId,alias,domain);
  if(error || !domain || !defaultAddress.includes("@")) throw new Error(error || "format");
  const guide = read(storage,businessId);
  const address = `${alias}@${domain}`;
  storage.setItem(invitationStorageKeys(businessId).guide,JSON.stringify({...guide,alias,address}));
  return address;
}

export function suggestedReceptionAliases(businessName: string, fallback: string): string[] {
  const slug = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"");
  const shorten = (value: string, length = 32) => value.slice(0,length).replace(/-+$/g,"");
  let base = shorten(slug(businessName) || slug(fallback));
  if(base.length < 3) base = `${base || "1"}-recibos`;
  const candidates = [base,base.replaceAll("-",""),`${shorten(base,24)}-recibos`,`${shorten(base,30)}-1`,`${shorten(base,30)}-2`];
  return [...new Set(candidates.filter(candidate=>aliasPattern.test(candidate)))].slice(0,3);
}
