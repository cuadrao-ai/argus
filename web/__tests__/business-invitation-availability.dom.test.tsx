import {afterAll,afterEach,beforeAll,expect,mock,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act,useEffect} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import type {GrantedSpace} from "@/lib/business-api";
import type {ChatShellBridge} from "@/components/chat/ChatWorkspace";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

mock.module("next/navigation",()=>({useSearchParams:()=>new URLSearchParams(),usePathname:()=>"/biz",useRouter:()=>({push:()=>{},replace:()=>{}})}));

const OWNER=["read","manage","assign_owner"];
const copy=english.workspace_setup_preview;
let businesses=0;
const space=(permissions:string[]):GrantedSpace=>({space_id:`66666666-6666-4666-8666-${String(businesses+=1).padStart(12,"0")}`,name:"La Palma",grant_id:`grant-${businesses}`,role:"owner",business_role:"owner",permissions,capabilities:["read","prepare","approve"],access_seen:true} as GrantedSpace);
const shell={currentView:"workspace",conversationId:null,isBelowTablet:false,sidebarCollapsed:false,memberEmail:"owner@example.test",showWorkspace:()=>undefined,newChat:()=>undefined,prepareQuestion:()=>undefined} as unknown as ChatShellBridge;

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz",width:1280,height:900});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{document.body.innerHTML="";businesses=0;});
afterAll(()=>GlobalRegistrator.unregister());

async function mountTree(tree:React.ReactNode){
 const i18n=i18next.createInstance();await i18n.init({lng:"en",resources:{en:{translation:english},"es-419":{translation:spanish}},interpolation:{escapeValue:false}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
 await act(async()=>root.render(<I18nextProvider i18n={i18n}>{tree}</I18nextProvider>));
 const settle=async(done:()=>boolean)=>{for(let turn=0;turn<80&&!done();turn+=1)await act(async()=>new Promise(resolve=>setTimeout(resolve,5)));expect(done()).toBe(true);};
 const button=(label:string)=>[...document.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent?.includes(label));
 const click=(element:HTMLElement|null|undefined)=>{expect(element).toBeTruthy();return act(async()=>element!.click());};
 const openMenu=async()=>{await click(document.querySelector<HTMLButtonElement>("button[aria-haspopup=menu]"));};
 return {host,settle,button,click,openMenu,unmount:()=>act(async()=>root.unmount())};
}

async function mountSwitchMenu(capability:()=>boolean){
 const {BusinessWorkspaceProvider,useBusiness}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 const chosen=space(OWNER);
 setChosenGrant(null);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[chosen],spaceDirectory:async()=>({spaces:[chosen],closed_spaces:[],invitations_available:capability()})};
 let reload:()=>void=()=>{};
 function Probe(){
  const workspace=useChatWorkspace();
  const business=useBusiness();
  reload=business.reload;
  const connect=workspace?.onShellChange;
  useEffect(()=>{connect?.(shell);},[connect]);
  return <header>{workspace?.sidebarHeader?.(shell)}</header>;
 }
 const page=await mountTree(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await page.settle(()=>document.querySelector("button[aria-haspopup=menu]")!==null);
 return {...page,reload,chosen};
}

async function mountAccessPreview(invitationsAvailable:boolean){
 const {BusinessContext}=await import("@/components/business-app/BusinessWorkspace");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {default:Access}=await import("@/app/design-workspace/BusinessAccessPreview");
 const chosen=space(OWNER);
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 globalThis.fetch=(async(url:string)=>{
  if(typeof url==="string"&&url.includes("/business/access")){
   return Response.json({grants:[{id:"g1",email:null,display_name:"Owner",capabilities:["read","prepare","approve"],created_at:"2026-10-01",owner:true,business_role:"owner",permissions:OWNER}],invites:[{id:"i1",email:"pending@example.test",created_at:"2026-10-01",expires_at:"2026-11-01",state:"pending",requested_role:"editor"}],invitations_available:invitationsAvailable});
  }
  return Response.json({});
 }) as unknown as typeof fetch;
 const context={source:{...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live"},chosen,reload:()=>{}} as never;
 const page=await mountTree(<BusinessContext.Provider value={context}><Access/></BusinessContext.Provider>);
 await page.settle(()=>page.host.querySelector("[data-testid=business-access-preview]")!==null);
 return page;
}

test("directory loading keeps the invite menu hidden",{timeout:10000},async()=>{
 const bag={done:false};
 const chosen=space(OWNER);
 const {BusinessWorkspaceProvider}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 setChosenGrant(null);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[chosen],spaceDirectory:()=>new Promise(resolve=>{const finish=()=>resolve({spaces:[chosen],closed_spaces:[],invitations_available:true});bag.done?finish():setTimeout(finish,80);})};
 function Probe(){const workspace=useChatWorkspace();useEffect(()=>{workspace?.onShellChange?.(shell);},[workspace]);return <header>{workspace?.sidebarHeader?.(shell)}</header>;}
 const page=await mountTree(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await page.settle(()=>document.querySelector("button[aria-haspopup=menu]")!==null);
 try{
  await page.openMenu();
  expect(page.button(copy.batch_title)).toBeUndefined();
  bag.done=true;
  await page.settle(()=>page.button(copy.batch_title)!==undefined);
 }finally{await page.unmount();}
});

test("capability loss on refetch closes the invite menu and modal",{timeout:10000},async()=>{
 let available=true;
 const page=await mountSwitchMenu(()=>available);
 try{
  await page.openMenu();
  await page.settle(()=>page.button(copy.batch_title)!==undefined);
  await page.click(page.button(copy.batch_title));
  await page.settle(()=>document.querySelector("[data-invitation-modal]")!==null);
  available=false;
  await act(async()=>page.reload());
  await page.openMenu();
  await page.settle(()=>document.querySelector("[data-invitation-modal]")===null);
  expect(page.button(copy.batch_title)).toBeUndefined();
 }finally{await page.unmount();}
});

test("failed directory read leaves invite actions hidden",{timeout:10000},async()=>{
 const chosen=space(OWNER);
 const {BusinessWorkspaceProvider}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 setChosenGrant(null);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[chosen],spaceDirectory:async()=>{throw new Error("offline");}};
 function Probe(){const workspace=useChatWorkspace();useEffect(()=>{workspace?.onShellChange?.(shell);},[workspace]);return <header>{workspace?.sidebarHeader?.(shell)}</header>;}
 const page=await mountTree(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await act(async()=>new Promise(resolve=>setTimeout(resolve,120)));
 try{
  const menu=document.querySelector<HTMLButtonElement>("button[aria-haspopup=menu]");
  if(menu)await page.click(menu);
  expect(page.button(copy.batch_title)).toBeUndefined();
  expect(page.host.textContent?.includes(copy.batch_title)).toBe(false);
 }finally{await page.unmount();}
});

test("live Acceso hides create and resend without capability",{timeout:10000},async()=>{
 const page=await mountAccessPreview(false);
 try{
  expect(page.host.textContent?.includes(copy.batch_title)).toBe(false);
  expect(page.host.textContent?.includes(copy.access_resend)).toBe(false);
 }finally{await page.unmount();}
});

test("live Acceso shows create when capability is true",{timeout:10000},async()=>{
 const page=await mountAccessPreview(true);
 try{
  expect(page.host.textContent?.includes(copy.batch_title)).toBe(true);
 }finally{await page.unmount();}
});
