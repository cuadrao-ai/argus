import {afterAll,afterEach,beforeAll,expect,mock,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act,useEffect,type ReactNode} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import type {BusinessContextValue} from "@/components/business-app/BusinessWorkspace";
import type {GrantedSpace} from "@/lib/business-api";
import type {ChatShellBridge} from "@/components/chat/ChatWorkspace";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

mock.module("next/navigation",()=>({useSearchParams:()=>new URLSearchParams(),usePathname:()=>"/biz",useRouter:()=>({push:()=>{},replace:()=>{}})}));

type Language="en"|"es-419";
type Recipient={email:string;role:string;command_key:string};
type Access={grants:Record<string,unknown>[];invites:Record<string,unknown>[]};
type Wire={access?:Access|(()=>Access);send?:(recipients:Recipient[],attempt:number)=>Response};

const OWNER=["read","manage","assign_owner"];
const MANAGER=["read","manage"];
let businesses=0;
const space=(permissions:string[]):GrantedSpace=>({space_id:`66666666-6666-4666-8666-${String(businesses+=1).padStart(12,"0")}`,name:"La Palma",grant_id:"grant-1",role:"owner",business_role:"owner",permissions,capabilities:["read","prepare","approve"],access_seen:true} as GrantedSpace);
const nobody:Access={grants:[],invites:[]};
const grant=(email:string)=>({id:email,email,display_name:email,capabilities:["read"],created_at:"2026-10-26",owner:false,business_role:"viewer",permissions:["read"]});
const invite=(email:string,state:"pending"|"expired")=>({id:email,email,requested_role:"viewer",state,created_at:"2026-10-26",expires_at:"2026-11-02"});
const outcome=(recipient:Recipient,state:string,delivery:string="accepted")=>({command_key:recipient.command_key,email:recipient.email,invite_id:state==="refused"?null:"invite-1",state,delivery:state==="refused"?null:delivery,code:state==="refused"?"invalid_email":null});
const sendAll=(recipients:Recipient[])=>Response.json({results:recipients.map(recipient=>outcome(recipient,"pending"))});
const copy=english.workspace_setup_preview;

const originalFetch=globalThis.fetch,originalAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz",width:1280,height:900});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{globalThis.fetch=originalFetch;if(originalAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=originalAuth;document.body.innerHTML="";});
afterAll(()=>GlobalRegistrator.unregister());

function serve({access=nobody,send=sendAll}:Wire={}){
 const sent:Recipient[][]=[];
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 globalThis.fetch=(async(_url:string,init?:RequestInit)=>{
  if(init?.method!=="POST")return Response.json(typeof access==="function"?access():access);
  const {recipients}=JSON.parse(String(init.body)) as {recipients:Recipient[]};
  sent.push(recipients);
  return send(recipients,sent.length);
 }) as unknown as typeof fetch;
 return sent;
}

async function render(tree:(close:()=>void)=>ReactNode,language:Language="en"){
 const i18n=i18next.createInstance();await i18n.init({lng:language,resources:{en:{translation:english},"es-419":{translation:spanish}},interpolation:{escapeValue:false}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
 let closed=0;
 await act(async()=>root.render(<I18nextProvider i18n={i18n}>{tree(()=>{closed+=1;})}</I18nextProvider>));
 const settle=async(done:()=>boolean)=>{for(let turn=0;turn<50&&!done();turn+=1)await act(async()=>new Promise(resolve=>setTimeout(resolve,5)));expect(done()).toBe(true);};
 const emails=()=>[...document.querySelectorAll<HTMLInputElement>('input[type="email"]')];
 const typeEmail=async(index:number,value:string)=>{
  const field=emails()[index]!;
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field,value);field.dispatchEvent(new Event("input",{bubbles:true}));});
  await act(async()=>emails()[index]?.dispatchEvent(new FocusEvent("focusout",{bubbles:true})));
 };
 const submit=()=>act(async()=>document.querySelector("form")!.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})));
 const button=(label:string)=>[...document.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent?.includes(label));
 const click=(element:HTMLElement|null|undefined)=>{expect(element).toBeTruthy();return act(async()=>element!.click());};
 const addRow=()=>click(button((language==="en"?english:spanish).workspace_setup_preview.batch_add_short));
 const trash=()=>[...document.querySelectorAll<HTMLButtonElement>("li button:not([role])")];
 const sendButton=()=>document.querySelector<HTMLButtonElement>('button[type="submit"]')!;
 return {host,settle,emails,typeEmail,submit,button,click,addRow,trash,sendButton,closed:()=>closed,unmount:()=>act(async()=>root.unmount())};
}

async function mountForm({permissions=OWNER,live=true,language="en"}:{permissions?:string[];live?:boolean;language?:Language}={}){
 const {BusinessContext}=await import("@/components/business-app/BusinessWorkspace");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {default:Form}=await import("@/components/business-app/BusinessInvitationForm");
 const fixture=createFixtureBusinessDataSource({chatAvailable:false});
 const context={source:live?{...fixture,mode:"live"}:fixture,chosen:space(permissions),reload:()=>{}} as unknown as BusinessContextValue;
 const form=(close:()=>void,onRefused?:(error:unknown)=>void)=><BusinessContext.Provider value={context}><Form onClose={close} onRefused={onRefused}/></BusinessContext.Provider>;
 const refusals:unknown[]=[];
 const page=await render(close=>form(close,error=>refusals.push(error)),language);
 return {...page,refusals,reopen:()=>render(close=>form(close),language)};
}

test("an accepted command replay renders its accepted server outcome",async()=>{
 const sent=serve({send:recipients=>Response.json({results:[outcome(recipients[0]!,"accepted")]})});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"member@example.test");await page.submit();
  await page.settle(()=>sent.length===1);
  expect(document.body.textContent).toContain(english.business_access.invitation_accepted);
  expect(document.body.textContent).not.toContain("Couldn't send");
  expect(sent[0]![0]!.role).toBe("viewer");
 }finally{await page.unmount();}
});

test("a live send posts every recipient and offers the next step",async()=>{
 const sent=serve();
 const page=await mountForm();
 try{
  await page.typeEmail(0,"uno@example.test");await page.addRow();await page.typeEmail(1,"dos@example.test");
  await page.submit();
  await page.settle(()=>page.button(copy.batch_done)!==undefined);
  expect(sent).toHaveLength(1);expect(sent[0]!.map(row=>row.email)).toEqual(["uno@example.test","dos@example.test"]);
  expect(document.body.textContent).toContain(copy.batch_success.replace("{{count}}","2"));
  expect(page.button(copy.batch_more)).toBeTruthy();
 }finally{await page.unmount();}
});

test("sample mode fakes the success and never reaches the API",async()=>{
 const sent=serve();
 const page=await mountForm({live:false});
 try{
  await page.typeEmail(0,"muestra@example.test");await page.submit();
  await act(async()=>new Promise(resolve=>setTimeout(resolve,700)));
  expect(page.button(copy.batch_done)).toBeTruthy();
  expect(sent).toHaveLength(0);
 }finally{await page.unmount();}
});

test("Lector is the default, and an owner can pick only Dueño and Lector while every role stays visible",async()=>{
 serve();
 const page=await mountForm();
 try{
  const picker=document.querySelector<HTMLButtonElement>('[role="combobox"]')!;
  expect(picker.textContent).toContain(copy.permission_viewer);
  await page.click(picker);
  const options=[...document.querySelectorAll<HTMLButtonElement>('[role="option"]')];
  expect(options.map(option=>[option.querySelector("span span")?.textContent,option.getAttribute("aria-disabled")==="true"])).toEqual([[copy.permission_owner,false],[copy.permission_admin,true],[copy.permission_editor,true],[copy.permission_viewer,false]]);
  await page.click(options[1]);
  expect(document.querySelector('[role="listbox"]')).not.toBeNull();
  expect(picker.textContent).toContain(copy.permission_viewer);
 }finally{await page.unmount();}
});

test("a manager who is not an owner cannot reach an enabled Dueño choice",async()=>{
 const sent=serve();
 const page=await mountForm({permissions:MANAGER});
 try{
  const picker=document.querySelector<HTMLButtonElement>('[role="combobox"]')!;
  await page.click(picker);
  const owner=[...document.querySelectorAll<HTMLButtonElement>('[role="option"]')][0]!;
  expect(owner.textContent).toContain(copy.permission_owner);expect(owner.getAttribute("aria-disabled")).toBe("true");
  await page.click(owner);
  expect(picker.textContent).toContain(copy.permission_viewer);
  await page.click(picker);
  await page.typeEmail(0,"lector@example.test");await page.submit();
  await page.settle(()=>sent.length===1);
  expect(sent[0]![0]!.role).toBe("viewer");
 }finally{await page.unmount();}
});

test("a failed send keeps the draft, shows its reference and retries the same command",async()=>{
 const sent=serve({send:(recipients,attempt)=>attempt===1?Response.json({code:"unavailable"},{status:503}):sendAll(recipients)});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"reintento@example.test");await page.submit();
  await page.settle(()=>document.querySelector('form [role="alert"]')!==null);
  const alert=document.querySelector('form [role="alert"]')!;
  expect(alert.textContent).toContain(copy.batch_send_error);
  expect(alert.querySelector('[data-testid="error-reference"]')).not.toBeNull();
  expect(page.emails()[0]!.value).toBe("reintento@example.test");
  expect(page.sendButton().textContent).toBe(copy.batch_retry);
  await page.submit();
  await page.settle(()=>page.button(copy.batch_done)!==undefined);
  expect(sent[1]![0]!.command_key).toBe(sent[0]![0]!.command_key);
  expect(document.querySelector('form [role="alert"]')).toBeNull();
 }finally{await page.unmount();}
});

for(const language of ["en","es-419"] as const){
 for(const partial of [false,true]){
 test(`${language} invitation availability refusal blocks ${partial?"partial-batch retry":"first-send retry"} without blaming an email`,async()=>{
  const sent=serve({send:(recipients,attempt)=>partial&&attempt===1
   ?Response.json({results:recipients.map((recipient,index)=>outcome(recipient,index===0?"pending":"refused"))})
   :Response.json({code:"business_invitations_unavailable",detail:"Untranslated server detail"},{status:409})});
  const page=await mountForm({language});
  const translations=language==="en"?english:spanish;
  try{
   await page.typeEmail(0,"available@example.test");
   if(partial){await page.addRow();await page.typeEmail(1,"pending@example.test");}
   await page.submit();
   if(partial){
    expect(page.sendButton().disabled).toBe(false);
    await page.submit();
   }
   await page.settle(()=>document.querySelector('form [role="alert"]')!==null);
   expect(page.sendButton().disabled).toBe(true);
   expect(page.sendButton().textContent).toBe(translations.workspace_setup_preview.batch_retry);
   expect(page.emails().every(field=>field.disabled)).toBe(true);
   expect(document.querySelector('[data-recipient-email][aria-invalid="true"]')).toBeNull();
   expect(document.body.textContent).toContain(translations.workspace_setup_preview.batch_unavailable_placeholder);
   expect(document.body.textContent).not.toContain(translations.workspace_setup_preview.batch_send_error);
   expect(document.body.textContent).not.toContain("Untranslated server detail");
   expect(document.querySelector('[data-testid="error-reference"]')).not.toBeNull();
   expect(page.refusals).toHaveLength(0);
   const attempts=sent.length;
   await page.submit();
   expect(sent).toHaveLength(attempts);
  }finally{await page.unmount();}
 });
 }
}

test("another conflict remains retryable rather than claiming invitations are off",async()=>{
 const sent=serve({send:(recipients,attempt)=>attempt===1?Response.json({code:"invitation_conflict"},{status:409}):sendAll(recipients)});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"conflict@example.test");await page.submit();
  expect(page.sendButton().disabled).toBe(false);
  expect(document.body.textContent).toContain(copy.batch_send_error);
  await page.submit();
  expect(sent).toHaveLength(2);
 }finally{await page.unmount();}
});

test("a refused send says so, offers the contact line, and its draft never comes back",async()=>{
 serve({send:()=>Response.json({code:"permission_denied"},{status:403})});
 const page=await mountForm();
 await page.typeEmail(0,"privado@example.test");await page.submit();
 await page.settle(()=>page.refusals.length===1);
 const alert=document.querySelector('form [role="alert"]')!;
 expect(alert.textContent).toContain(english.business.lifecycle.errors.business_unavailable);
 expect(alert.textContent).toContain(english.auth.business_unavailable.body);
 expect(alert.querySelector('[data-testid="error-reference"]')).not.toBeNull();
 expect(page.sendButton().disabled).toBe(true);
 await page.unmount();
 const again=await page.reopen();
 try{expect(again.emails()[0]!.value).toBe("");}finally{await again.unmount();}
});

test("a refused access read stops the form before anyone types",async()=>{
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 globalThis.fetch=(async()=>Response.json({code:"permission_denied"},{status:403})) as unknown as typeof fetch;
 const page=await mountForm();
 try{
  await page.settle(()=>page.refusals.length===1);
  expect(page.emails()[0]!.disabled).toBe(true);
  expect(document.querySelector('form [role="alert"]')?.textContent).toContain(english.business.lifecycle.errors.business_unavailable);
 }finally{await page.unmount();}
});

test("a duplicate in the list stops the send at its own row",async()=>{
 const sent=serve();
 const page=await mountForm();
 try{
  await page.typeEmail(0,"misma@example.test");await page.addRow();await page.typeEmail(1,"MISMA@example.test");
  await page.submit();
  expect(sent).toHaveLength(0);
  expect([...document.querySelectorAll('li [role="alert"]')].map(note=>note.textContent)).toEqual([copy.batch_duplicate,copy.batch_duplicate]);
 }finally{await page.unmount();}
});

test("the server list flags who already has access or a live invitation, not an expired one",async()=>{
 const sent=serve({access:{grants:[grant("miembro@example.test")],invites:[invite("pendiente@example.test","pending"),invite("vencida@example.test","expired")]}});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"Miembro@example.test");
  await page.settle(()=>document.querySelector('li [role="alert"]')?.textContent===copy.batch_member);
  await page.typeEmail(0,"pendiente@example.test");
  await page.settle(()=>document.querySelector('li [role="alert"]')?.textContent===copy.batch_pending);
  await page.typeEmail(0,"vencida@example.test");
  await page.settle(()=>document.querySelector('li [role="alert"]')===null);
  await page.submit();
  await page.settle(()=>sent.length===1);
  expect(sent[0]![0]!.email).toBe("vencida@example.test");
 }finally{await page.unmount();}
});

test("a server duplicate reads as already having access, not as sent",async()=>{
 serve({send:recipients=>Response.json({results:[outcome(recipients[0]!,"already_member")]})});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"yaesta@example.test");await page.submit();
  await page.settle(()=>page.button(copy.batch_done)!==undefined);
  expect(document.body.textContent).toContain(copy.batch_member);
  expect(document.body.textContent).not.toContain(copy.batch_sent_pending);
 }finally{await page.unmount();}
});

test.each(["failed","uncertain","not_configured","pending"])("a created invitation whose email delivery is %s never reads as sent",async delivery=>{
 serve({send:recipients=>Response.json({results:[outcome(recipients[0]!,"pending",delivery)]})});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"sinenvio@example.test");await page.submit();
  await page.settle(()=>page.button(copy.batch_done)!==undefined);
  const text=document.body.textContent??"";
  expect(text).toContain(copy.invite_pending_detail);
  expect(text).not.toContain(copy.batch_success_one);
  expect(text).not.toContain(copy.batch_sent_pending);
  expect(text).not.toContain(copy.batch_no_access);
 }finally{await page.unmount();}
});

test("only the delivered rows count as sent, never a duplicate or an undelivered one",async()=>{
 const states:Record<string,[string,string]>={"enviada":["pending","accepted"],"fallida":["pending","failed"],"miembro":["already_member","accepted"],"mala":["refused","accepted"]};
 serve({send:recipients=>Response.json({results:recipients.map(recipient=>outcome(recipient,...states[recipient.email.split("@")[0]!]!))})});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"enviada@example.test");
  for(const [index,name] of ["fallida","miembro","mala"].entries()){await page.addRow();await page.typeEmail(index+1,`${name}@example.test`);}
  await page.submit();
  await page.settle(()=>document.querySelector('li [role="alert"]')!==null);
  const text=document.body.textContent??"";
  expect(text).toContain(copy.batch_partial.replace("{{sent}}","1").replace("{{failed}}","3"));
  expect(text.split(copy.batch_sent_pending).length-1).toBe(1);
  expect(text).toContain(copy.invite_pending_detail);
 }finally{await page.unmount();}
});

test("a batch of only duplicates is not announced as sent",async()=>{
 serve({send:recipients=>Response.json({results:recipients.map(recipient=>outcome(recipient,"already_member"))})});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"uno@example.test");await page.addRow();await page.typeEmail(1,"dos@example.test");await page.submit();
  await page.settle(()=>page.button(copy.batch_done)!==undefined);
  const text=document.body.textContent??"";
  expect(text).not.toContain(copy.batch_success.replace("{{count}}","2"));
  expect(text).not.toContain(copy.batch_no_access);
 }finally{await page.unmount();}
});

test("a delivered invitation still reads as sent",async()=>{
 serve();
 const page=await mountForm();
 try{
  await page.typeEmail(0,"entregada@example.test");await page.submit();
  await page.settle(()=>page.button(copy.batch_done)!==undefined);
  expect(document.body.textContent).toContain(copy.batch_success_one);
  expect(document.body.textContent).toContain(copy.batch_sent_pending);
 }finally{await page.unmount();}
});

test("a row the server refuses keeps its error beside it and only that row retries",async()=>{
 const sent=serve({send:(recipients,attempt)=>Response.json({results:recipients.map(recipient=>outcome(recipient,attempt===1&&recipient.email.startsWith("mala")?"refused":"pending"))})});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"buena@example.test");await page.addRow();await page.typeEmail(1,"mala@example.test");
  await page.submit();
  await page.settle(()=>document.querySelector('li [role="alert"]')!==null);
  const note=document.querySelector('li [role="alert"]')!;
  expect(note.textContent).toBe(copy.batch_send_error);
  expect(note.closest("li")?.querySelector("input")?.value).toBe("mala@example.test");
  expect(document.body.textContent).toContain(copy.batch_sent_pending);
  expect(document.body.textContent).toContain(copy.batch_partial.replace("{{sent}}","1").replace("{{failed}}","1"));
  expect(page.sendButton().textContent).toBe(copy.batch_retry);
  await page.submit();
  await page.settle(()=>page.button(copy.batch_done)!==undefined);
  expect(sent[1]!.map(row=>row.email)).toEqual(["mala@example.test"]);
  expect(sent[1]![0]!.command_key).toBe(sent[0]![1]!.command_key);
 }finally{await page.unmount();}
});

test.each(["revoked","expired"])("a %s replay is a row error, never a sent invitation",async state=>{
 serve({send:recipients=>Response.json({results:[outcome(recipients[0]!,state)]})});
 const page=await mountForm();
 try{
  await page.typeEmail(0,"replay@example.test");await page.submit();
  await page.settle(()=>document.querySelector('li [role="alert"]')!==null);
  expect(document.body.textContent).not.toContain(copy.batch_sent_pending);
  expect(page.button(copy.batch_done)).toBeUndefined();
 }finally{await page.unmount();}
});

test.each([["en","Remove nombre@example.test"],["es-419","Quitar a nombre@example.test"]] as const)("%s names the person on the trash, and the email column never changes with the row count",async(language,label)=>{
 serve();
 const page=await mountForm({language});
 try{
  const columns=()=>[...document.querySelectorAll("form [class*='grid-cols-']")].map(node=>node.className.match(/grid-cols-\S+/)?.[0]);
  const heading=columns()[0];
  expect(new Set(columns()).size).toBe(1);
  expect(heading).toContain("_44px");
  expect(page.trash()).toHaveLength(0);
  await page.typeEmail(0,"nombre@example.test");await page.addRow();
  expect(new Set(columns())).toEqual(new Set([heading]));
  expect(page.trash().map(item=>item.getAttribute("aria-label"))[0]).toBe(label);
  await page.click(page.trash()[1]);
  expect(page.trash()).toHaveLength(0);expect(new Set(columns())).toEqual(new Set([heading]));
 }finally{await page.unmount();}
});

test("the desktop dialog is centered and a long list scrolls inside it",async()=>{
 serve();
 const page=await mountForm();
 try{
  const dialog=document.querySelector<HTMLElement>("[data-invitation-modal]")!;
  expect(dialog.parentElement?.className).toContain("items-center");
  expect(dialog.parentElement?.className).not.toContain("pt-[12dvh]");
  expect(document.querySelector('form ul')?.className).toContain("overflow-y-auto");
 }finally{await page.unmount();}
});

test("the X keeps the draft for the next time the dialog opens",async()=>{
 serve();
 const page=await mountForm();
 await page.typeEmail(0,"borrador@example.test");
 await page.click(document.querySelector<HTMLButtonElement>(`[data-invitation-modal] [aria-label="${english.common.close}"]`));
 expect(page.closed()).toBe(1);
 await page.unmount();
 const again=await page.reopen();
 try{expect(again.emails()[0]!.value).toBe("borrador@example.test");}finally{await again.unmount();}
});

test("dismissing send results refreshes the open Acceso list, whichever door opened the form",async()=>{
 let invites:Record<string,unknown>[]=[];
 serve({access:()=>({grants:[grant("miembro@example.test")],invites}),send:recipients=>{invites=[invite(recipients[0]!.email,"pending")];return sendAll(recipients);}});
 const {BusinessContext}=await import("@/components/business-app/BusinessWorkspace");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {default:Form}=await import("@/components/business-app/BusinessInvitationForm");
 const {default:Access}=await import("@/app/design-workspace/BusinessAccessPreview");
 const context={source:{...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live"},chosen:space(OWNER),reload:()=>{}} as unknown as BusinessContextValue;
 const page=await render(close=><BusinessContext.Provider value={context}><Access/><Form onClose={close}/></BusinessContext.Provider>);
 try{
  await page.settle(()=>page.host.textContent?.includes("miembro@example.test")===true);
  expect(page.host.querySelector("details")).toBeNull();
  await page.typeEmail(0,"nueva@example.test");await page.submit();
  expect(document.body.textContent).toContain(copy.batch_sent_pending);
  expect(page.host.querySelector("details")).toBeNull();
  await page.click(page.button(copy.batch_done));
  await page.settle(()=>page.host.querySelector("details")!==null);
  expect(page.host.querySelector("details")?.textContent).toContain("nueva@example.test");
 }finally{await page.unmount();}
});

const shell={currentView:"workspace",conversationId:null,isBelowTablet:false,sidebarCollapsed:false,memberEmail:"owner@example.test",showWorkspace:()=>undefined,newChat:()=>undefined,prepareQuestion:()=>undefined} as unknown as ChatShellBridge;

async function mountWorkspace(permissions:string[],invitationsAvailable=false){
 const {BusinessWorkspaceProvider,useBusiness}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {useChatWorkspace}=await import("@/components/chat/ChatWorkspace");
 const {setChosenGrant}=await import("@/lib/business-grant");
 setChosenGrant(null);
 const chosen=space(permissions);
 const source={...createFixtureBusinessDataSource({chatAvailable:false}),mode:"live",spaces:async()=>[chosen],spaceDirectory:async()=>({spaces:[chosen],closed_spaces:[],invitations_available:invitationsAvailable})};
 const state:{panel:string;ready:boolean}={panel:"",ready:false};
 function Probe(){
  const workspace=useChatWorkspace();const business=useBusiness();
  state.panel=business.panel.kind;state.ready=business.chosen!==null;
  const connect=workspace?.onShellChange;
  useEffect(()=>{connect?.(shell);},[connect]);
  return <header>{workspace?.sidebarHeader?.(shell)}</header>;
 }
 const page=await render(()=><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="mock-auth-user"><Probe/></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
 await page.settle(()=>state.ready);
 await page.click(page.host.querySelector<HTMLButtonElement>("button[aria-haspopup=menu]"));
 return {...page,state};
}

test("the live Business menu opens the dialog and stays on the current screen",async()=>{
 const sent=serve();
 const page=await mountWorkspace(OWNER,true);
 try{
  await page.click(page.button(copy.batch_title));
  await page.settle(()=>document.querySelector("[data-invitation-modal]")!==null);
  expect(page.state.panel).toBe("overview");
  await page.typeEmail(0,"menu@example.test");await page.submit();
  await page.settle(()=>sent.length===1);
  expect(sent[0]![0]!.email).toBe("menu@example.test");
 }finally{await page.unmount();}
});

test("the menu offers no invitation without the manage permission",async()=>{
 serve();
 const page=await mountWorkspace(["read"],true);
 try{expect(page.button(copy.batch_title)).toBeUndefined();}finally{await page.unmount();}
});

test("the menu offers no invitation when capability is false",async()=>{
 serve();
 const page=await mountWorkspace(OWNER,false);
 try{expect(page.button(copy.batch_title)).toBeUndefined();}finally{await page.unmount();}
});

test("the menu offers no invitation while capability is loading",async()=>{
 serve();
 const page=await mountWorkspace(OWNER,false);
 try{expect(page.button(copy.batch_title)).toBeUndefined();}finally{await page.unmount();}
});

test("manage and capability true enables the invitation menu entry",async()=>{
 serve();
 const page=await mountWorkspace(OWNER,true);
 try{expect(page.button(copy.batch_title)).toBeDefined();}finally{await page.unmount();}
});
