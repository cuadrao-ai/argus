import {afterAll,afterEach,beforeAll,expect,mock,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import type {GrantedSpace} from "@/lib/business-api";
import english from "@/public/locales/en/common.json";

mock.module("next/navigation",()=>({useSearchParams:()=>new URLSearchParams(),usePathname:()=>"/biz",useRouter:()=>({push:()=>{},replace:()=>{}})}));

const copy=english.workspace_setup_preview;
const PERMISSIONS={
 owner:["read","prepare","approve","manage","download","export","assign_owner"],
 admin:["read","prepare","approve","manage","download","export"],
 editor:["read","prepare","download","export"],
 viewer:["read"],
} as const;
type Role=keyof typeof PERMISSIONS;
const LABEL:Record<Role,string>={owner:copy.permission_owner,admin:copy.permission_admin,editor:copy.permission_editor,viewer:copy.permission_viewer};
const member=(role:Role)=>({id:`grant-${role}`,email:`${role}@example.test`,display_name:null,capabilities:["read"],created_at:"2026-11-26",owner:role==="owner",business_role:role,permissions:PERMISSIONS[role]});
const everyone=(Object.keys(PERMISSIONS) as Role[]).map(member);

const originalFetch=globalThis.fetch,originalAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz",width:1280,height:900});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{globalThis.fetch=originalFetch;if(originalAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=originalAuth;document.body.innerHTML="";});
afterAll(()=>GlobalRegistrator.unregister());

/** The Acceso list as the server gives it to a person in `role`, who is the row `grant-${role}`. */
async function mountAcceso(role:Role){
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 globalThis.fetch=(async()=>Response.json({grants:everyone,invites:[],invitations_available:true})) as unknown as typeof fetch;
 const {BusinessContext}=await import("@/components/business-app/BusinessWorkspace");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {default:Access}=await import("@/app/design-workspace/BusinessAccessPreview");
 const chosen={space_id:`space-${role}`,name:"La Palma",grant_id:`grant-${role}`,role:role==="owner"?"owner":"accountant",business_role:role,permissions:[...PERMISSIONS[role]],capabilities:["read"],access_seen:true} as GrantedSpace;
 const context={source:{...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live"},chosen,reload:()=>{}} as never;
 const i18n=i18next.createInstance();await i18n.init({lng:"en",resources:{en:{translation:english}},interpolation:{escapeValue:false}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
 await act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Access/></BusinessContext.Provider></I18nextProvider>));
 for(let turn=0;turn<100&&!host.querySelector("li");turn+=1)await act(async()=>new Promise(resolve=>setTimeout(resolve,5)));
 const row=(of:Role)=>[...host.querySelectorAll("li")].find(item=>item.textContent?.includes(`${of}@example.test`))!;
 const picker=(of:Role)=>row(of).querySelector<HTMLButtonElement>('[role="combobox"]');
 const offered=async(of:Role)=>{
  await act(async()=>picker(of)!.click());
  const labels=[...document.querySelectorAll('[role="option"]')].map(option=>[option.querySelector("span span")?.textContent,option.getAttribute("aria-disabled")==="true"]);
  await act(async()=>picker(of)!.click());
  return labels;
 };
 return {host,row,picker,offered,unmount:()=>act(async()=>root.unmount())};
}

test("a Dueño may give a member any of the four roles",async()=>{
 const page=await mountAcceso("owner");
 try{
  expect(await page.offered("editor")).toEqual([[LABEL.owner,false],[LABEL.admin,false],[LABEL.editor,false],[LABEL.viewer,false]]);
 }finally{await page.unmount();}
});

test("an Administrador may give Administrador, Editor or Lector, and only reads a Dueño's role",async()=>{
 const page=await mountAcceso("admin");
 try{
  expect(await page.offered("viewer")).toEqual([[LABEL.admin,false],[LABEL.editor,false],[LABEL.viewer,false]]);
  expect(page.picker("owner")).toBeNull();
  expect(page.row("owner").textContent).toContain(LABEL.owner);
 }finally{await page.unmount();}
});

test.each(["editor","viewer"] as const)("a person who cannot manage sees no role picker: %s",async role=>{
 const page=await mountAcceso(role);
 try{
  expect(page.host.querySelector('[role="combobox"]')).toBeNull();
  for(const of of Object.keys(PERMISSIONS) as Role[])expect(page.row(of).textContent).toContain(LABEL[of]);
 }finally{await page.unmount();}
});
