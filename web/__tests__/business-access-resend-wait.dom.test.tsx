import {afterAll,afterEach,beforeAll,expect,mock,setSystemTime,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import type {GrantedSpace} from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";

mock.module("next/navigation",()=>({useSearchParams:()=>new URLSearchParams(),usePathname:()=>"/biz",useRouter:()=>({push:()=>{},replace:()=>{}})}));

const REENVIAR=spanish.workspace_setup_preview.access_resend;
const reenviarEn=(seconds:number)=>spanish.auth.signup.confirmation_resend_wait.replace("{{seconds}}",String(seconds));
const OWNER=["read","prepare","approve","manage","download","export","assign_owner"];
const owner={id:"grant-owner",email:"owner@example.test",display_name:null,capabilities:["read"],created_at:"2026-11-26",owner:true,business_role:"owner",permissions:OWNER};
const invite=(name:string,wait?:number)=>({id:`invite-${name}`,email:`${name}@example.test`,created_at:"2026-11-26T00:00:00Z",expires_at:"2026-12-03T00:00:00Z",state:"pending",requested_role:"viewer",...(wait===undefined?{}:{resend_wait_seconds:wait})});
const list=(...invites:ReturnType<typeof invite>[])=>({grants:[owner],invites,invitations_available:true});

const originalFetch=globalThis.fetch,originalAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz",width:1280,height:900});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{setSystemTime();globalThis.fetch=originalFetch;if(originalAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=originalAuth;document.body.innerHTML="";});
afterAll(()=>GlobalRegistrator.unregister());

/** Acceso for a Dueño. `listed` is what the server lists; `resend` answers each Reenviar. */
async function mountAcceso(listed:ReturnType<typeof list>,resend:()=>Response=()=>Response.json(listed)){
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 const resends:string[]=[];
 globalThis.fetch=(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input);
  if(init?.method==="POST"&&url.endsWith("/resend")){resends.push(url);return resend();}
  return Response.json(listed);
 }) as unknown as typeof fetch;
 const {BusinessContext}=await import("@/components/business-app/BusinessWorkspace");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {default:Access}=await import("@/app/design-workspace/BusinessAccessPreview");
 const chosen={space_id:"space-owner",name:"La Palma",grant_id:"grant-owner",role:"owner",business_role:"owner",permissions:OWNER,capabilities:["read"],access_seen:true} as GrantedSpace;
 const context={source:{...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live"},chosen,reload:()=>{}} as never;
 const i18n=i18next.createInstance();await i18n.init({lng:"es-419",resources:{"es-419":{translation:spanish}},interpolation:{escapeValue:false}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
 await act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Access/></BusinessContext.Provider></I18nextProvider>));
 const settle=async(until:()=>boolean,turns=100)=>{for(let turn=0;turn<turns&&!until();turn+=1)await act(async()=>new Promise(resolve=>setTimeout(resolve,20)));};
 await settle(()=>Boolean(host.querySelector("li")));
 /** The Reenviar button on the row of `name`: the first button of its row. */
 const reenviar=(name:string)=>[...host.querySelectorAll("li")].find(item=>item.textContent?.includes(`${name}@example.test`))!.querySelector<HTMLButtonElement>("button")!;
 return {host,reenviar,resends,settle,unmount:()=>act(async()=>root.unmount())};
}

test("Reenviar shows the seconds the server says, is disabled, and comes back at zero",async()=>{
 const answered=new Date("2026-11-27T12:00:00Z");
 setSystemTime(answered);
 const page=await mountAcceso(list(invite("larga",42),invite("corta",1),invite("libre",0)));
 try{
  expect(page.reenviar("larga").textContent).toBe(reenviarEn(42));
  expect(page.reenviar("larga").disabled).toBe(true);
  expect(page.reenviar("corta").textContent).toBe(reenviarEn(1));
  expect(page.reenviar("corta").disabled).toBe(true);
  expect(page.reenviar("libre").textContent).toBe(REENVIAR);
  expect(page.reenviar("libre").disabled).toBe(false);
  setSystemTime(new Date(answered.getTime()+1_000));
  await page.settle(()=>page.reenviar("corta").textContent===REENVIAR);
  expect(page.reenviar("corta").textContent).toBe(REENVIAR);
  expect(page.reenviar("corta").disabled).toBe(false);
  expect(page.reenviar("larga").textContent).toBe(reenviarEn(41));
  expect(page.reenviar("larga").disabled).toBe(true);
  setSystemTime(new Date(answered.getTime()+42_000));
  await page.settle(()=>!page.reenviar("larga").disabled);
  expect(page.reenviar("larga").textContent).toBe(REENVIAR);
 }finally{await page.unmount();}
});

test("a resend starts the wait the server answers with",async()=>{
 const page=await mountAcceso(list(invite("ana",0)),()=>Response.json(list(invite("ana",60))));
 try{
  await act(async()=>page.reenviar("ana").click());
  await page.settle(()=>page.reenviar("ana").disabled);
  expect(page.resends.length).toBe(1);
  expect(page.reenviar("ana").textContent).toBe(reenviarEn(60));
  expect(page.reenviar("ana").disabled).toBe(true);
 }finally{await page.unmount();}
});

test("a 429 with Retry-After starts the countdown on that invitation and shows no failure",async()=>{
 const refusal=()=>Response.json({code:"business_invite_resend_cooldown",context:{retry_after_seconds:37}},{status:429,headers:{"Retry-After":"37"}});
 const page=await mountAcceso(list(invite("ana"),invite("luis")),refusal);
 try{
  await act(async()=>page.reenviar("ana").click());
  await page.settle(()=>page.reenviar("ana").disabled);
  expect(page.reenviar("ana").textContent).toBe(reenviarEn(37));
  expect(page.reenviar("ana").disabled).toBe(true);
  expect(page.reenviar("luis").textContent).toBe(REENVIAR);
  expect(page.reenviar("luis").disabled).toBe(false);
  expect(page.host.querySelector('[role="alert"]')).toBeNull();
 }finally{await page.unmount();}
});

test("a 429 with no wait says the email was not sent and starts no countdown",async()=>{
 const refusal=()=>Response.json({code:"business_invite_send_cap_reached",context:{retry_after_seconds:0}},{status:429,headers:{"Retry-After":"0"}});
 const page=await mountAcceso(list(invite("ana")),refusal);
 try{
  await act(async()=>page.reenviar("ana").click());
  await page.settle(()=>Boolean(page.host.querySelector('p[role="status"]')));
  expect(page.host.querySelector('p[role="status"]')?.textContent).toBe(spanish.business_access.delivery_failed);
  expect(page.reenviar("ana").textContent).toBe(REENVIAR);
  expect(page.host.querySelector('[role="alert"]')).toBeNull();
 }finally{await page.unmount();}
});
