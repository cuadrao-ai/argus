import { z } from "zod";
import { authenticatedRequestHeaders } from "./chat-auth-ownership";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "./browser-auth-generation";
import { ARGUS_API_BASE_URL, argusApiRequestHeaders, serverRequestId } from "./argus-api-transport";
import { getChosenGrant } from "./business-grant";
import type { IdentityAppearance, IdentityCrop } from "./identity-appearance";

const crop = z.object({ mode: z.enum(["fit", "fill"]), zoom: z.number().min(1).max(4), x: z.number().min(-1).max(1), y: z.number().min(-1).max(1) });
const appearance = z.discriminatedUnion("kind", [z.object({ kind: z.literal("default") }), z.object({ kind: z.literal("avatar"), token: z.enum(["ocean", "ember", "gold", "slate", "teal", "indigo", "plum"]), mark: z.enum(["initials", "icon"]) }), z.object({ kind: z.literal("image"), asset_id: z.string(), crop })]);
const image = z.object({ asset_id: z.string(), width: z.number(), height: z.number(), source_url: z.string().nullable(), rendered_url: z.string().nullable() });
const details = z.object({ address: z.string().default(""), province: z.string().default(""), municipality: z.string().default(""), email: z.string().default(""), phone: z.string().default(""), website: z.string().default(""), description: z.string().default("") });
const profile = z.object({ space_id: z.string(), name: z.string(), country: z.enum(["DO", "US", "CA"]), currency: z.string(), revision: z.number().int().nonnegative(), details, appearance, image: image.nullable() });
export type BusinessProfile = z.infer<typeof profile>;
export type BusinessProfilePatch = { expected_revision: number; name?: string; details?: Partial<BusinessProfile["details"]>; appearance?: BusinessProfile["appearance"] };
type Scope = { selection: string | null; grant: string | null; userId?:string };
const currentScope = (): Scope => ({ selection: getChosenGrant(), grant: getChosenGrant() });

/** Pin both the selected context and the header before auth resolves. A late reply cannot update another Business. */
export async function businessSettingsRequest<T>(path: string, options: RequestInit = {}, scope = currentScope()): Promise<T> {
  const generation = browserAuthGeneration();
  const check = () => { options.signal?.throwIfAborted(); requireBrowserAuthGeneration(generation); if (getChosenGrant() !== scope.selection) throw new Error("Business selection changed"); };
  const auth = await authenticatedRequestHeaders(scope.userId);
  check();
  const headers = argusApiRequestHeaders(options.headers, auth, path);
  if (scope.grant) headers.set("X-Business-Grant", scope.grant);
  else headers.delete("X-Business-Grant");
  const response = await fetch(`${ARGUS_API_BASE_URL}${path}`, { ...options, headers, credentials: "include", cache: "no-store" });
  check();
  const text = await response.text();
  const body = text ? JSON.parse(text) : undefined;
  check();
  if (!response.ok) {
    throw Object.assign(new Error("Business settings unavailable"), { status: response.status, code: body.code ?? "unknown", requestId: serverRequestId(response, body) });
  }
  return body;
}
const profilePath = (id: string) => `/business/spaces/${encodeURIComponent(id)}/profile`;
function selectedProfile(value:unknown,id:string){
  const saved=profile.parse(value);
  if(saved.space_id!==id)throw new Error("Business profile target changed");
  return saved;
}
export async function getBusinessProfile(id: string, signal?: AbortSignal, scope?: Scope): Promise<BusinessProfile> {
  return selectedProfile(await businessSettingsRequest(profilePath(id), { signal }, scope),id);
}
export async function saveBusinessProfile(id: string, patch: BusinessProfilePatch, key: string, scope?: Scope): Promise<BusinessProfile> {
  const result = selectedProfile(await businessSettingsRequest(profilePath(id), { method: "PATCH", headers: { "Idempotency-Key": key }, body: JSON.stringify(patch) }, scope),id);
  return result;
}
const savedAppearances = new Map<string, IdentityAppearance>();
const imageSources = new Map<string,{source:string;rendered:string}>();
const appearanceStates=new Map<string,"loading"|"ready"|"failed">();
const appearanceRevisions=new Map<string,number>();
const listeners = new Set<() => void>();
export const subscribeBusinessAppearance = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const businessAppearanceSnapshot = (id: string) => savedAppearances.get(`${browserAuthGeneration()}:${id}`) ?? null;
export const businessAppearanceState = (id:string) => appearanceStates.get(`${browserAuthGeneration()}:${id}`)??null;
export function beginBusinessAppearance(id:string){appearanceStates.set(`${browserAuthGeneration()}:${id}`,"loading");for(const listener of listeners)listener();}
export function failBusinessAppearance(id:string){appearanceStates.set(`${browserAuthGeneration()}:${id}`,"failed");for(const listener of listeners)listener();}
export function profileIdentity(profile: BusinessProfile): IdentityAppearance {
  if (profile.appearance.kind !== "image") return profile.appearance;
  const bytes=profile.image?imageSources.get(`${browserAuthGeneration()}:${profile.image.asset_id}`):null;
  if (!profile.image || !bytes) return { kind: "default" };
  return { kind: "image", source: bytes.source, rendered: bytes.rendered, width: profile.image.width, height: profile.image.height, crop: profile.appearance.crop };
}
async function imageDataUrl(url:string,signal?:AbortSignal){
  if(!["http:","https:"].includes(new URL(url).protocol))throw new Error("Invalid Business image URL");
  signal?.throwIfAborted();
  const controller=new AbortController(),abort=()=>controller.abort();
  signal?.addEventListener("abort",abort,{once:true});
  const deadline=setTimeout(abort,15000);
  try{
    const response=await fetch(url,{signal:controller.signal,credentials:"omit",referrerPolicy:"no-referrer",cache:"no-store"});
    if(!response.ok)throw new Error("Business image unavailable");
    const blob=await response.blob();
    if(!["image/jpeg","image/png","image/webp"].includes(blob.type)||blob.size>1024*1024)throw new Error("Invalid Business image");
    return await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>typeof reader.result==="string"?resolve(reader.result):reject(new Error("Invalid Business image"));reader.onerror=()=>reject(reader.error);reader.readAsDataURL(blob);});
  }finally{clearTimeout(deadline);signal?.removeEventListener("abort",abort);}
}
export async function publishBusinessAppearance(value: BusinessProfile,signal?:AbortSignal) {
  const generation=browserAuthGeneration();
  const target=`${generation}:${value.space_id}`;
  if((appearanceRevisions.get(target)??-1)>value.revision)return;
  appearanceRevisions.set(target,value.revision);
  if(value.appearance.kind==="image"&&!value.image?.rendered_url){failBusinessAppearance(value.space_id);return;}
  if(value.appearance.kind==="image"&&value.image?.rendered_url){
    appearanceStates.set(target,"loading");for(const listener of listeners)listener();
    try{
      const rendered=await imageDataUrl(value.image.rendered_url,signal);
      const source=value.image.source_url?await imageDataUrl(value.image.source_url,signal):rendered;
      signal?.throwIfAborted();requireBrowserAuthGeneration(generation);
      if(appearanceRevisions.get(target)!==value.revision)return;
      imageSources.set(`${generation}:${value.image.asset_id}`,{source,rendered});
    }catch{if(!signal?.aborted&&browserAuthGeneration()===generation&&appearanceRevisions.get(target)===value.revision)failBusinessAppearance(value.space_id);return;}
  }
  signal?.throwIfAborted();requireBrowserAuthGeneration(generation);
  if(appearanceRevisions.get(target)!==value.revision)return;
  savedAppearances.set(target, profileIdentity(value));
  appearanceStates.set(`${generation}:${value.space_id}`,"ready");
  for (const listener of listeners) listener();
}
type AppearanceCommandState = { upload:string;save:string;asset_id?:string;crop?:IdentityCrop;revision?:number };
export function appearanceCommand(id: string, value: IdentityAppearance, saved?: BusinessProfile, scope = currentScope(), state:AppearanceCommandState = {upload:crypto.randomUUID(),save:crypto.randomUUID()}, onProgress?:()=>void) {
  let asset: { asset_id: string } | undefined = state.asset_id?{asset_id:state.asset_id}:undefined;
  return async () => {
    state.revision ??= saved?.revision ?? (await getBusinessProfile(id, undefined, scope)).revision;
    onProgress?.();
    let next: BusinessProfile["appearance"];
    if (value.kind !== "image") next = value;
    else {
      state.crop=value.crop;onProgress?.();
      if (saved?.appearance.kind === "image" && saved.image && (saved.image.source_url === value.source || imageSources.get(`${browserAuthGeneration()}:${saved.image.asset_id}`)?.source===value.source)) asset = saved.image;
      if (!asset) {
        const blob = await (await fetch(value.source)).blob();
        asset = z.object({ asset_id: z.string() }).parse(await businessSettingsRequest(`/business/spaces/${encodeURIComponent(id)}/appearance/assets`, { method: "POST", headers: { "Idempotency-Key": state.upload, "Content-Type": blob.type }, body: blob }, scope));
        state.asset_id=asset.asset_id;onProgress?.();
      }
      next = { kind: "image", asset_id: asset.asset_id, crop: value.crop satisfies IdentityCrop };
    }
    try{return await saveBusinessProfile(id, { expected_revision: state.revision, appearance: next }, state.save, scope);}
    catch(error){if(error&&typeof error==="object"&&"status" in error&&error.status===409){state.revision=undefined;state.save=crypto.randomUUID();onProgress?.();}throw error;}
  };
}
const createdSpace = z.object({ id: z.string(), name: z.string(), country: z.enum(["DO", "US", "CA"]), currency: z.string(), logo_url: z.string().nullable() });
export const businessCreationState = z.object({key:z.string().min(1),upload:z.string().min(1),save:z.string().min(1),asset_id:z.string().optional(),crop:crop.optional(),revision:z.number().int().nonnegative().optional(),created:z.object({id:z.string()}).optional()});
export type BusinessCreationState = z.infer<typeof businessCreationState>;
export function createBusinessCommand(input: { name: string; country: "DO" | "US" | "CA"; appearance: IdentityAppearance;userId?:string }, restored?: BusinessCreationState, onProgress?: (state:BusinessCreationState)=>void) {
  const state = restored ?? {key:crypto.randomUUID(),upload:crypto.randomUUID(),save:crypto.randomUUID()};
  const key = state.key, selection = getChosenGrant();
  let created: {id:string} | undefined = state.created;
  let finishAppearance: ReturnType<typeof appearanceCommand> | undefined;
  return {
    get created() { return created; },
    async run() {
      onProgress?.(state);
      created ??= createdSpace.parse(await businessSettingsRequest("/business/spaces", { method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ name: input.name, country: input.country }) }, { selection, grant: selection,userId:input.userId }));
      state.created={id:created.id};onProgress?.(state);
      const directory = z.object({ spaces: z.array(z.object({ space_id: z.string(), grant_id: z.string() })) }).parse(await businessSettingsRequest("/business/spaces", {}, { selection, grant: selection,userId:input.userId }));
      const selected = directory.spaces.find(item => item.space_id === created?.id);
      if (!selected) throw new Error("Created Business is not accessible");
      let accepted:BusinessProfile|undefined;
      if(state.asset_id&&state.crop&&input.appearance.kind==="default"){
        state.revision??=(await getBusinessProfile(created.id,undefined,{selection,grant:selected.grant_id,userId:input.userId})).revision;
        onProgress?.(state);
        try{accepted=await saveBusinessProfile(created.id,{expected_revision:state.revision,appearance:{kind:"image",asset_id:state.asset_id,crop:state.crop}},state.save,{selection,grant:selected.grant_id,userId:input.userId});}
        catch(error){if(error&&typeof error==="object"&&"status" in error&&error.status===409){state.revision=undefined;state.save=crypto.randomUUID();onProgress?.(state);}throw error;}
      }else if (input.appearance.kind !== "default") {
        finishAppearance ??= appearanceCommand(created.id, input.appearance, undefined, { selection, grant: selected.grant_id,userId:input.userId },state,()=>onProgress?.(state));
        accepted=await finishAppearance();
      }
      accepted??=await getBusinessProfile(created.id,undefined,{selection,grant:selected.grant_id,userId:input.userId});
      return {id:created.id,name:accepted.name,country:accepted.country,currency:accepted.currency,logo_url:null,grant_id:selected.grant_id};
    },
  };
}
