import {afterAll,afterEach,beforeAll,expect,mock,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act,useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import type {GrantedSpace} from "@/lib/business-api";
import type {ChatShellBridge} from "@/components/chat/ChatWorkspace";
import {businessAccessChangedEvent} from "@/app/design-workspace/businessAccessPreviewState";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

mock.module("next/navigation",()=>({useSearchParams:()=>new URLSearchParams(),usePathname:()=>"/biz",useRouter:()=>({push:()=>{},replace:()=>{}})}));

const OWNER=["read","manage","assign_owner"];
const VIEWER=["read"];
const copy=english.workspace_setup_preview;
let businesses=0;
const space=(permissions:string[],name?:string):GrantedSpace=>({space_id:`66666666-6666-4666-8666-${String(businesses+=1).padStart(12,"0")}`,name:name??"La Palma",grant_id:`grant-${businesses}`,role:"owner",business_role:"owner",permissions,capabilities:["read","prepare","approve"],access_seen:true} as GrantedSpace);
const desktopShell:ChatShellBridge={currentView:"workspace",conversationId:null,isBelowTablet:false,sidebarCollapsed:false,memberEmail:"owner@example.test",showWorkspace:()=>undefined,newChat:()=>undefined,prepareQuestion:()=>undefined} as ChatShellBridge;
const mobileShell:ChatShellBridge={...desktopShell,isBelowTablet:true,sidebarCollapsed:true} as ChatShellBridge;

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz",width:1280,height:900});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{document.body.innerHTML="";businesses=0;});
afterAll(()=>GlobalRegistrator.unregister());

async function mountTree(tree:React.ReactNode){
 const i18n=i18next.createInstance();await i18n.init({lng:"en",resources:{en:{translation:english},"es-419":{translation:spanish}},interpolation:{escapeValue:false}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
 await act(async()=>root.render(<I18nextProvider i18n={i18n}>{tree}</I18nextProvider>));
 const settle=async(done:()=>boolean)=>{for(let turn=0;turn<200&&!done();turn+=1)await act(async()=>new Promise(resolve=>setTimeout(resolve,5)));expect(done()).toBe(true);};
 const button=(label:string)=>[...document.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent?.includes(label));
 const click=(element:HTMLElement|null|undefined)=>{expect(element).toBeTruthy();return act(async()=>element!.click());};
 const openMenu=async()=>{await click(document.querySelector<HTMLButtonElement>("button[aria-haspopup=menu]"));};
 return {host,settle,button,click,openMenu,unmount:()=>act(async()=>root.unmount())};
}

async function mountSwitcher(shell:ChatShellBridge,capability:()=>boolean,permissions=OWNER){
 const {BusinessWorkspaceProvider,useBusiness}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 const chosen=space(permissions);
 setChosenGrant(null);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[chosen],spaceDirectory:async()=>({spaces:[chosen],closed_spaces:[],invitations_available:capability()})};
 let reload:()=>void=()=>{};
 let choose=(_grant:string|null)=>{};
 function Probe(){
  const workspace=useChatWorkspace();
  const business=useBusiness();
  reload=business.reload;
  choose=grant=>{if(grant)business.chooseBusiness?.(grant);};
  useEffect(()=>{workspace?.onShellChange?.(shell);},[workspace]);
  if(shell.isBelowTablet)return <>{workspace?.headerLeading?.(shell)}</>;
  return <header>{workspace?.sidebarHeader?.(shell)}</header>;
 }
 const page=await mountTree(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await page.settle(()=>document.querySelector("button[aria-haspopup=menu]")!==null);
 return {...page,reload,chosen,choose};
}

type AccessWire={invitations_available:boolean;permissions?:string[]};

function installAccessFetch(states:()=>AccessWire,options?:{delayMs?:number;fail?:boolean}){
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 globalThis.fetch=(async(url:string)=>{
  if(typeof url!=="string"||!url.includes("/business/access"))return Response.json({});
  if(options?.fail)return Response.json({code:"service_unavailable"},{status:503});
  if(options?.delayMs)await new Promise(resolve=>setTimeout(resolve,options.delayMs));
  const wire=states();
  const permissions=wire.permissions??OWNER;
  return Response.json({grants:[{id:"g1",email:null,display_name:"Owner",capabilities:["read","prepare","approve"],created_at:"2026-10-01",owner:true,business_role:"owner",permissions}],invites:[{id:"i1",email:"pending@example.test",created_at:"2026-10-01",expires_at:"2026-11-01",state:"pending",requested_role:"editor"}],invitations_available:wire.invitations_available});
 }) as unknown as typeof fetch;
}

async function mountLiveAcceso(states:()=>AccessWire,permissions=OWNER,options?:{delayMs?:number;fail?:boolean;skipFetchSetup?:boolean}){
 if(!options?.skipFetchSetup)installAccessFetch(states,options);
 const {BusinessContext}=await import("@/components/business-app/BusinessWorkspace");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {default:Access}=await import("@/app/design-workspace/BusinessAccessPreview");
 const chosen=space(permissions);
 const context={source:{...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live"},chosen,reload:()=>window.dispatchEvent(new Event(businessAccessChangedEvent))} as never;
 const page=await mountTree(<BusinessContext.Provider value={context}><Access/></BusinessContext.Provider>);
 await page.settle(()=>page.host.querySelector("[data-testid=business-access-preview]")!==null);
 return page;
}

test("desktop sidebar hides invite until directory is ready",{timeout:10000},async()=>{
 const bag={done:false};
 const chosen=space(OWNER);
 const {BusinessWorkspaceProvider}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 setChosenGrant(null);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[chosen],spaceDirectory:()=>new Promise(resolve=>{const finish=()=>resolve({spaces:[chosen],closed_spaces:[],invitations_available:true});bag.done?finish():setTimeout(finish,60);})};
 function Probe(){const workspace=useChatWorkspace();useEffect(()=>{workspace?.onShellChange?.(desktopShell);},[workspace]);return <header>{workspace?.sidebarHeader?.(desktopShell)}</header>;}
 const page=await mountTree(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await page.settle(()=>document.querySelector("button[aria-haspopup=menu]")!==null);
 try{
  await page.openMenu();
  expect(page.button(copy.batch_title)).toBeUndefined();
  bag.done=true;
  await page.settle(()=>page.button(copy.batch_title)!==undefined);
 }finally{await page.unmount();}
});

test("mobile header follows the same invite readiness rules",{timeout:10000},async()=>{
 let available=false;
 const page=await mountSwitcher(mobileShell,()=>available);
 try{
  await page.openMenu();
  expect(page.button(copy.batch_title)).toBeUndefined();
  await page.click(document.querySelector("button[aria-haspopup=menu]"));
  available=true;
  await act(async()=>page.reload());
  await page.settle(()=>document.querySelector("button[aria-haspopup=menu]")!==null);
  await page.openMenu();
  await page.settle(()=>page.button(copy.batch_title)!==undefined);
  expect(page.button(copy.batch_title)).toBeDefined();
 }finally{await page.unmount();}
});

test("invite hides as soon as directory reload starts",{timeout:10000},async()=>{
 const available=true;
 let hold=true;
 const chosen=space(OWNER);
 const {BusinessWorkspaceProvider}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 setChosenGrant(null);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[chosen],spaceDirectory:()=>new Promise(resolve=>{const finish=()=>resolve({spaces:[chosen],closed_spaces:[],invitations_available:available});if(hold)setTimeout(finish,120);else finish();})};
 let reload=()=>{};
 const {useBusiness}=await import("@/components/business-app/BusinessWorkspace");
 function Probe(){const workspace=useChatWorkspace();const business=useBusiness();reload=business.reload;useEffect(()=>{workspace?.onShellChange?.(desktopShell);},[workspace]);return <header>{workspace?.sidebarHeader?.(desktopShell)}</header>;}
 const page=await mountTree(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await page.settle(()=>document.querySelector("button[aria-haspopup=menu]")!==null);
 try{
  await page.openMenu();
  await page.settle(()=>page.button(copy.batch_title)!==undefined);
  await page.click(document.querySelector("button[aria-haspopup=menu]"));
  await act(async()=>reload());
  await page.openMenu();
  expect(page.button(copy.batch_title)).toBeUndefined();
  hold=false;
  await page.settle(()=>page.button(copy.batch_title)!==undefined);
 }finally{await page.unmount();}
});

test("directory reload error keeps invite closed",{timeout:10000},async()=>{
 let fail=false;
 const chosen=space(OWNER);
 const {BusinessWorkspaceProvider,useBusiness}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 setChosenGrant(null);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[chosen],spaceDirectory:()=>fail?Promise.reject(new Error("directory down")):Promise.resolve({spaces:[chosen],closed_spaces:[],invitations_available:true})};
 let reload=()=>{};
 function Probe(){const workspace=useChatWorkspace();const business=useBusiness();reload=business.reload;useEffect(()=>{workspace?.onShellChange?.(desktopShell);},[workspace]);return <header>{workspace?.sidebarHeader?.(desktopShell)}</header>;}
 const page=await mountTree(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await page.settle(()=>document.querySelector("button[aria-haspopup=menu]")!==null);
 try{
  await page.openMenu();
  await page.settle(()=>page.button(copy.batch_title)!==undefined);
  await page.click(document.querySelector("button[aria-haspopup=menu]"));
  fail=true;
  await act(async()=>reload());
  await page.openMenu();
  await page.settle(()=>page.button(copy.batch_title)===undefined);
 }finally{await page.unmount();}
});

test("manage permission is required on desktop and mobile",{timeout:10000},async()=>{
 for (const shell of [desktopShell, mobileShell]) {
  const page=await mountSwitcher(shell,()=>true,VIEWER);
  try{
    await page.openMenu();
    expect(page.button(copy.batch_title)).toBeUndefined();
  }finally{await page.unmount();}
 }
});

test("capability loss closes the modal on desktop and mobile",{timeout:10000},async()=>{
 for (const shell of [desktopShell, mobileShell]) {
  let available=true;
  const page=await mountSwitcher(shell,()=>available);
  try{
    await page.openMenu();
    await page.settle(()=>page.button(copy.batch_title)!==undefined);
    await page.click(page.button(copy.batch_title));
    await page.settle(()=>document.querySelector("[data-invitation-modal]")!==null);
    available=false;
    await act(async()=>page.reload());
    await page.settle(()=>document.querySelector("[data-invitation-modal]")===null);
    if(shell.isBelowTablet)await page.openMenu();
    else await page.openMenu();
    expect(page.button(copy.batch_title)).toBeUndefined();
  }finally{await page.unmount();}
 }
});

test("switching businesses erases the previous draft and does not restore it",{timeout:15000},async()=>{
 const {BusinessWorkspaceProvider,useBusiness}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {default:Form}=await import("@/components/business-app/BusinessInvitationForm");
 const {peekInvitationDraftEmails}=await import("@/components/business-app/BusinessInvitationForm");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 const businessA=space(OWNER,"Negocio A");
 const businessB=space(OWNER,"Negocio B");
 businessB.grant_id="grant-b";
 setChosenGrant(businessA.grant_id);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[businessA,businessB],spaceDirectory:async()=>({spaces:[businessA,businessB],closed_spaces:[],invitations_available:true})};
 function Probe(){
  const workspace=useChatWorkspace();
  const business=useBusiness();
  const [show,setShow]=useState(true);
  useEffect(()=>{workspace?.onShellChange?.(desktopShell);},[workspace]);
  return <>
    <header>{workspace?.sidebarHeader?.(desktopShell)}</header>
    {show&&business.chosen?.space_id===businessA.space_id?<Form onClose={()=>setShow(false)}/>:null}
    <button type="button" data-testid="pick-b" onClick={()=>business.chooseBusiness(businessB.grant_id)}>pick B</button>
    <button type="button" data-testid="pick-a" onClick={()=>business.chooseBusiness(businessA.grant_id)}>pick A</button>
  </>;
 }
 const page=await mountTree(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await page.settle(()=>document.querySelector("[data-invitation-modal]")!==null);
 const field=document.querySelector<HTMLInputElement>("[data-recipient-email]");
 await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field,"deja-a@example.test");field?.dispatchEvent(new Event("input",{bubbles:true}));});
 expect(peekInvitationDraftEmails(businessA.space_id)).toContain("deja-a@example.test");
 await page.click(page.host.querySelector("[data-testid=pick-b]"));
 await page.settle(()=>peekInvitationDraftEmails(businessA.space_id).length===0);
 await page.click(page.host.querySelector("[data-testid=pick-a]"));
 await page.settle(()=>document.querySelector("[data-testid=pick-a]")!==null);
 expect(peekInvitationDraftEmails(businessA.space_id)).toEqual([]);
 try{await page.unmount();}catch{/* already unmounted in flow */}
});

test("live Acceso hides create and resend when capability is false",{timeout:10000},async()=>{
 const page=await mountLiveAcceso(()=>({invitations_available:false}));
 try{
  expect(page.button(copy.batch_title)).toBeUndefined();
  expect(page.button(copy.access_resend)).toBeUndefined();
 }finally{await page.unmount();}
});

test("live Acceso shows create and resend only while readiness is true",{timeout:10000},async()=>{
 const page=await mountLiveAcceso(()=>({invitations_available:true}));
 try{
  expect(page.button(copy.batch_title)).toBeDefined();
  expect(page.button(copy.access_resend)).toBeDefined();
 }finally{await page.unmount();}
});

test("live Acceso refetch drops invite actions at reload start",{timeout:10000},async()=>{
 let available=true;
 const page=await mountLiveAcceso(()=>({invitations_available:available}));
 try{
  expect(page.button(copy.access_resend)).toBeDefined();
  available=false;
  await act(async()=>window.dispatchEvent(new Event(businessAccessChangedEvent)));
  await page.settle(()=>page.button(copy.access_resend)===undefined&&page.button(copy.batch_title)===undefined);
 }finally{await page.unmount();}
});

test("live Acceso non-403 failure clears invite affordances",{timeout:10000},async()=>{
 let calls=0;
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 globalThis.fetch=(async(url:string)=>{
  if(typeof url!=="string"||!url.includes("/business/access"))return Response.json({});
  calls+=1;
  if(calls>1)return Response.json({code:"upstream"},{status:503});
  return Response.json({grants:[{id:"g1",email:null,display_name:"Owner",capabilities:["read","prepare","approve"],created_at:"2026-10-01",owner:true,business_role:"owner",permissions:OWNER}],invites:[{id:"i1",email:"pending@example.test",created_at:"2026-10-01",expires_at:"2026-11-01",state:"pending",requested_role:"editor"}],invitations_available:true});
 }) as unknown as typeof fetch;
 const page=await mountLiveAcceso(()=>({invitations_available:true}),OWNER,{skipFetchSetup:true});
 try{
  expect(page.button(copy.access_resend)).toBeDefined();
  await act(async()=>window.dispatchEvent(new Event(businessAccessChangedEvent)));
  await page.settle(()=>page.button(copy.batch_title)===undefined&&page.button(copy.access_resend)===undefined);
 }finally{await page.unmount();}
});

test("live Acceso viewer keeps member admin minus invite surfaces",{timeout:10000},async()=>{
 const page=await mountLiveAcceso(()=>({invitations_available:true}),VIEWER);
 try{
  expect(page.button(copy.batch_title)).toBeUndefined();
  expect(page.button(copy.access_resend)).toBeUndefined();
  expect(page.host.textContent?.includes("pending@example.test")).toBe(true);
 }finally{await page.unmount();}
});

test.each(["failed delivery","partial refusal"])("live Acceso retains %s results until dismissal",async outcome=>{
 const originalFetch=globalThis.fetch;
 const sent:{email:string;command_key:string}[][]=[];
 const delivered=new Set<string>();
 let reads=0;
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 globalThis.fetch=(async(url:string,init?:RequestInit)=>{
  if(typeof url!=="string"||!url.includes("/business/access"))return Response.json({});
  if(init?.method==="POST"){
   const {recipients}=JSON.parse(String(init.body)) as {recipients:{email:string;command_key:string}[]};
   sent.push(recipients);
   return Response.json({results:recipients.map((row,index)=>{
    const refused=outcome==="partial refusal"&&sent.length===1&&index===1;
    if(!refused)delivered.add(row.email);
    return {...row,invite_id:refused?null:`invite-${index}`,state:refused?"refused":"pending",delivery:outcome==="failed delivery"?"failed":"accepted",code:refused?"invalid_recipient":null};
   })});
  }
  reads+=1;
  return Response.json({grants:[],invites:[...delivered].map((email,index)=>({id:`invite-${index}`,email,state:"pending",created_at:"2026-11-08",expires_at:"2026-11-15",requested_role:"viewer"})),invitations_available:true});
 }) as typeof fetch;
 const page=await mountLiveAcceso(()=>({invitations_available:true}),OWNER,{skipFetchSetup:true});
 const typeEmail=async(index:number,email:string)=>{
  const field=document.querySelectorAll<HTMLInputElement>("[data-recipient-email]")[index];
  expect(field).toBeDefined();
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field,email);field!.dispatchEvent(new Event("input",{bubbles:true}));});
 };
 const submit=()=>act(async()=>document.querySelector("[data-invitation-modal] form")!.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})));
 try{
  await page.click(page.button(copy.batch_title));
  await page.settle(()=>document.querySelector("[data-invitation-modal]")!==null);
  await typeEmail(0,"first@example.test");
  if(outcome==="partial refusal"){
   await page.click(page.button(copy.batch_add_short));
   await typeEmail(1,"retry@example.test");
  }
  await submit();
  await page.settle(()=>sent.length===1);
  expect(document.querySelector("[data-invitation-modal]")).not.toBeNull();
  if(outcome==="failed delivery")expect(document.body.textContent).toContain(english.business_access.delivery_failed);
  else{
   expect(page.button(copy.batch_retry)).toBeDefined();
   expect(document.querySelector<HTMLInputElement>("[data-recipient-email]")?.value).toBe("retry@example.test");
   await submit();
   await page.settle(()=>sent.length===2);
   expect(sent[1]!.map(row=>row.email)).toEqual(["retry@example.test"]);
   expect(sent[1]![0]!.command_key).toBe(sent[0]![1]!.command_key);
  }
  const beforeClose=reads;
  await page.click(page.button(copy.batch_done));
  await page.settle(()=>document.querySelector("[data-invitation-modal]")===null&&reads>beforeClose);
  expect(page.host.textContent).toContain("first@example.test");
 }finally{await page.unmount();globalThis.fetch=originalFetch;}
});
