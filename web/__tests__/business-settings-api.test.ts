import { afterEach, expect, test } from "bun:test";
import { acceptBusinessInvitation, changeBusinessRole, getBusinessDirectory, inviteBusinessMembers, revokeBusinessAccessGrant } from "@/lib/business-api";
import { setChosenGrant } from "@/lib/business-grant";
import { businessAppearanceState,createBusinessCommand, getBusinessProfile,publishBusinessAppearance,saveBusinessProfile } from "@/lib/business-profile-api";

const originalFetch = globalThis.fetch;
const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
afterEach(() => {
  globalThis.fetch = originalFetch;
  setChosenGrant(null);
  if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock;
});
const profile = { space_id: "second", name: "Taller Luna", country: "DO", currency: "DOP", revision: 3, details: { address: "Calle Sol" }, appearance: { kind: "default" }, image: null };
test("directory keeps the canonical role and permissions for a second Owner Business", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async () => Response.json({ spaces: [{ space_id: "second", name: "Taller Luna", grant_id: "grant-2", role: "owner", business_role: "owner", permissions: ["read", "manage"], capabilities: ["read", "prepare", "approve"], access_seen: true }] });
  expect((await getBusinessDirectory()).spaces[0]).toMatchObject({ business_role: "owner", permissions: ["read", "manage"] });
});
test("profile saves send the exact revision, key and selected Owner grant", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  setChosenGrant("grant-2");
  const calls: RequestInit[] = [];
  globalThis.fetch = async (_url, init) => { calls.push(init!); return Response.json(profile); };
  expect(await getBusinessProfile("second")).toMatchObject(profile);
  await saveBusinessProfile("second", { expected_revision: 3, details: { address: "Calle Sol" } }, "save-1");
  expect(new Headers(calls[1].headers).get("X-Business-Grant")).toBe("grant-2");
  expect(new Headers(calls[1].headers).get("Idempotency-Key")).toBe("save-1");
  expect(JSON.parse(String(calls[1].body))).toEqual({ expected_revision: 3, details: { address: "Calle Sol" } });
});
test("appearance failure retries the same new Business without another create", async () => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  let creates = 0, saves = 0;
  globalThis.fetch = async (url, init) => {
    const path = String(url);
    if (path.endsWith("/spaces") && init?.method === "POST") { creates++; return Response.json({ id: "second", name: profile.name, country: "DO", currency: "DOP", logo_url: null }); }
    if (path.endsWith("/spaces")) return Response.json({ spaces: [{ space_id: "second", name: profile.name, grant_id: "grant-2", role: "owner", business_role: "owner", permissions: ["read", "manage"], capabilities: ["read", "prepare", "approve"], access_seen: true }] });
    if (init?.method === "PATCH" && ++saves === 1) return Response.json({ code: "storage_unavailable" }, { status: 503 });
    return Response.json(profile);
  };
  const command = createBusinessCommand({ name: profile.name, country: "DO", appearance: { kind: "avatar", token: "teal", mark: "initials" } });
  await expect(command.run()).rejects.toThrow();
  expect(command.created?.id).toBe("second");
  expect((await command.run()).grant_id).toBe("grant-2");
  expect(creates).toBe(1);
});
test("selection change before auth completion prevents any request",async()=>{
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";setChosenGrant("grant-one");
 let requests=0;globalThis.fetch=async()=>{requests++;return Response.json(profile);};
 const pending=getBusinessProfile("first");setChosenGrant("grant-two");
 await expect(pending).rejects.toThrow("Business selection changed");expect(requests).toBe(0);
});
test("a late profile reply cannot confirm state under another Business",async()=>{
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";setChosenGrant("grant-one");
 let reply:((response:Response)=>void)|undefined;
 globalThis.fetch=()=>new Promise(resolve=>{reply=resolve;});
 const pending=saveBusinessProfile("first",{expected_revision:3,details:{phone:"809 555 0100"}},"same-save");
 await Promise.resolve();setChosenGrant("grant-two");reply?.(Response.json(profile));
 await expect(pending).rejects.toThrow("Business selection changed");
});
test("delete accepts the actual 204 contract and role promotion stays pending in returned state",async()=>{
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 const access={grants:[{id:"editor",email:"member@example.test",display_name:"Member",business_role:"editor",permissions:["read","prepare"],capabilities:["read","prepare"],created_at:"2026-10-26",owner:false}],invites:[{id:"promotion",email:"member@example.test",requested_role:"admin",state:"pending",created_at:"2026-10-26",expires_at:"2026-11-02"}]};
 globalThis.fetch=async(_url,init)=>init?.method==="DELETE"?new Response(null,{status:204}):Response.json(access);
 await revokeBusinessAccessGrant("other");
 const pending=await changeBusinessRole("editor","admin");expect(pending.grants[0].business_role).toBe("editor");expect(pending.invites[0].requested_role).toBe("admin");
});
test("batch invitations keep selected roles and recipient acceptance targets the exact Business",async()=>{
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 const calls:{url:string;body:unknown}[]=[];
 globalThis.fetch=async(url,init)=>{calls.push({url:String(url),body:JSON.parse(String(init?.body))});return Response.json(String(url).endsWith("/accept")?{space_id:"second",grant_id:"accepted-grant"}:{results:[{command_key:"member-key",email:"team@example.test",invite_id:"invite-one",state:"pending",delivery:"uncertain",code:null}]});};
 const result=await inviteBusinessMembers([{email:"team@example.test",role:"viewer",command_key:"member-key"}]);
 expect(calls[0].body).toEqual({recipients:[{email:"team@example.test",role:"viewer",command_key:"member-key"}]});expect(result.results[0].delivery).toBe("uncertain");
 const accepted=await acceptBusinessInvitation({id:"invite-one",space_id:"second",name:"Taller Luna",requested_role:"viewer",expires_at:"2026-11-02"});expect(calls[1].body).toEqual({space_id:"second"});expect(accepted.grant_id).toBe("accepted-grant");
});
test("reload after a lost appearance reply reuses the committed Business and exact save command",async()=>{
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 let creates=0,revision=3;
 let checkpoint:Parameters<typeof createBusinessCommand>[1];
 const patches:{key:string|null;body:unknown}[]=[];
 globalThis.fetch=async(url,init)=>{
  if(String(url).endsWith("/spaces")&&init?.method==="POST"){creates++;return Response.json({id:"second",name:profile.name,country:"DO",currency:"DOP",logo_url:null});}
  if(String(url).endsWith("/spaces"))return Response.json({spaces:[{space_id:"second",grant_id:"grant-2"}]});
  if(init?.method==="PATCH"){
   patches.push({key:new Headers(init.headers).get("Idempotency-Key"),body:JSON.parse(String(init.body))});
   if(patches.length===1){revision++;throw new TypeError("Reply lost after commit");}
  }
  return Response.json({...profile,revision});
 };
 const input={name:profile.name,country:"DO" as const,appearance:{kind:"avatar" as const,token:"teal" as const,mark:"initials" as const}};
 const first=createBusinessCommand(input,undefined,state=>{checkpoint=JSON.parse(JSON.stringify(state));});
 await expect(first.run()).rejects.toThrow("Reply lost");
 const remount=createBusinessCommand(input,checkpoint);
 await remount.run();
 expect(creates).toBe(1);expect(patches).toHaveLength(2);expect(patches[1]).toEqual(patches[0]);
});
test("profile transport does not start asset reads without a mounted owner",async()=>{
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";const calls:string[]=[];
 globalThis.fetch=async url=>{calls.push(String(url));if(!String(url).includes("/profile"))return new Promise(()=>{});return Response.json({...profile,space_id:"owned-image-target",appearance:{kind:"image",asset_id:"asset-one",crop:{mode:"fit",zoom:1,x:0,y:0}},image:{asset_id:"asset-one",width:64,height:32,source_url:"http://127.0.0.1:4412/assets/source",rendered_url:"http://127.0.0.1:4412/assets/rendered"}});};
 await saveBusinessProfile("owned-image-target",{expected_revision:3},"profile-only");
 expect(calls).toHaveLength(1);
});
test("a saved image without readable bytes stays failed rather than becoming a default avatar",async()=>{
 await publishBusinessAppearance({...profile,space_id:"unreadable-image",appearance:{kind:"image",asset_id:"missing-render",crop:{mode:"fit",zoom:1,x:0,y:0}},image:null});
 expect(businessAppearanceState("unreadable-image")).toBe("failed");
});
