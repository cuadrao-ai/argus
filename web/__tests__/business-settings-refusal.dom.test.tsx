import {afterAll,afterEach,beforeAll,expect,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import type {BusinessContextValue} from "../components/business-app/BusinessWorkspace";
import messages from "../public/locales/en/common.json";

const id="55555555-5555-4555-8555-555555555555";
const profile={space_id:id,name:"Private Business",country:"DO",currency:"DOP",revision:1,details:{address:"Private address",email:"contact@example.test"},appearance:{kind:"default"},image:null};
const fiscal={name:profile.name,tax_id:{type:"rnc",value:"131245678"},can_edit:true};
const member={id:"member",email:"member@example.test",display_name:"Member",business_role:"editor",permissions:["read","prepare"],capabilities:["read","prepare"],created_at:"2026-10-26",owner:false};
const access={grants:[member],invites:[{id:"pending",email:"pending@example.test",requested_role:"viewer",state:"pending",created_at:"2026-10-26",expires_at:"2026-11-02"}]};
const denied=(status=403)=>Response.json({code:"permission_denied"},{status});
const unavailable=()=>Response.json({code:"unavailable"},{status:503});
const originalFetch=globalThis.fetch,originalAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz",settings:{navigation:{disableChildFrameNavigation:true}}});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{globalThis.fetch=originalFetch;if(originalAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=originalAuth;document.body.innerHTML="";});
afterAll(async()=>GlobalRegistrator.unregister());

async function mount(kind:"profile"|"access"){
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 const {createRoot}=await import("react-dom/client");
 const {BusinessContext}=await import("../components/business-app/BusinessWorkspace");
 const {createFixtureBusinessDataSource}=await import("../components/business-app/fixture-data");
 const {setChosenGrant}=await import("../lib/business-grant");setChosenGrant("selected-owner");
 const Component=kind==="profile"?(await import("../app/design-workspace/BusinessProfilePreview")).default:(await import("../app/design-workspace/BusinessAccessPreview")).default;
 const context={source:{...createFixtureBusinessDataSource({chatAvailable:true}),mode:"live"},chosen:{space_id:id,grant_id:"selected-owner",name:profile.name,role:"owner",business_role:"owner",permissions:["read","manage","assign_owner"]},records:{workspace:{country:"DO"}},reload:()=>{},actions:{create:[]}} as unknown as BusinessContextValue;
 const i18n=i18next.createInstance();await i18n.init({lng:"en",resources:{en:{translation:messages}}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
 await act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Component/></BusinessContext.Provider></I18nextProvider>));
 const button=(text:string)=>[...document.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent?.includes(text));
 const click=async(element:HTMLElement|undefined|null)=>{expect(element).toBeTruthy();await act(async()=>element?.click());};
 const type=async(name:string,value:string)=>act(async()=>{const field=document.querySelector<HTMLInputElement>(name.startsWith("input[")?name:`[name="${name}"]`);expect(field).toBeTruthy();Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field,value);field?.dispatchEvent(new Event("input",{bubbles:true}));});
 const settle=async(done:()=>boolean)=>{for(let n=0;n<50&&!done();n++)await act(async()=>new Promise(resolve=>setTimeout(resolve,10)));expect(done()).toBe(true);};
 return {host,button,click,type,settle,close:()=>act(async()=>root.unmount())};
}

test.each(["action","refresh"] as const)("access %s refusal removes loaded members, invitations and dialogs",async failure=>{
 let reads=0;
 globalThis.fetch=async(_url,init)=>{
  if(init?.method==="DELETE")return failure==="action"?denied():new Response(null,{status:204});
  reads++;return reads===1?Response.json(access):denied();
 };
 const page=await mount("access");
 try{
  expect(page.host.textContent).toContain(member.email);
  await page.click(page.host.querySelector<HTMLButtonElement>(`button[aria-label="${messages.workspace_setup_preview.access_remove_for.replace("{{email}}",member.email)}"]`));
  await page.click(document.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]'));
  await page.settle(()=>document.querySelector('[role="alert"]')!==null);
  expect(document.body.textContent).not.toContain(member.email);expect(document.body.textContent).not.toContain("pending@example.test");
  expect(document.querySelector('[role="alertdialog"]')).toBeNull();expect(page.button(messages.workspace_setup_preview.invite)).toBeUndefined();
 }finally{await page.close();}
});

test("a confirmed revocation followed by unavailable refresh never claims removal failed",async()=>{
 let reads=0;
 globalThis.fetch=async(_url,init)=>init?.method==="DELETE"?new Response(null,{status:204}):++reads===1?Response.json(access):unavailable();
 const page=await mount("access");
 try{
  await page.click(page.host.querySelector<HTMLButtonElement>(`button[aria-label="${messages.workspace_setup_preview.access_remove_for.replace("{{email}}",member.email)}"]`));await page.click(document.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]'));
  await page.settle(()=>page.host.querySelector('[role="alert"]')!==null);
  expect(page.host.textContent).not.toContain(member.email);expect(page.host.textContent).not.toContain(messages.business_access.remove_error);
  expect(page.host.textContent).toContain(messages.business_access.error);expect(page.button(messages.common.retry)).toBeTruthy();
 }finally{await page.close();}
});

test.each(["profile-action","profile-refresh","fiscal-action","fiscal-read"] as const)("%s refusal removes loaded profile, fiscal facts and open draft",async failure=>{
 let profileReads=0,fiscalReads=0;
 globalThis.fetch=async(url,init)=>{
  if(String(url).endsWith("/fiscal-profile")){
   if(init?.method==="PATCH")return failure==="fiscal-action"?denied():Response.json(fiscal);
   return ++fiscalReads>1&&failure==="fiscal-read"?denied():Response.json(fiscal);
  }
  if(init?.method==="PATCH")return denied();
  return ++profileReads>1&&failure==="profile-refresh"?denied():Response.json(profile);
 };
 const page=await mount("profile");
 try{
  expect(page.host.textContent).toContain("Private address");expect(page.host.textContent).toContain("131245678");
  if(failure==="profile-action"){
   await page.click(page.button("Location and contact"));await page.type("profile-address","Attempted private edit");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]'));
  }else{
   await page.click(page.button("Identity and tax details"));
   if(failure!=="fiscal-read"){await page.type("business-name","Attempted private edit");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]'));}
  }
  await page.settle(()=>document.querySelector('[role="alert"]')!==null);
  expect(document.body.textContent).not.toContain("Private address");expect(document.body.textContent).not.toContain("131245678");expect(document.body.textContent).not.toContain("contact@example.test");
  expect(page.host.querySelector('[data-testid="business-profile-preview"]')).toBeNull();expect(document.querySelector('[data-testid="side-drawer"]')).toBeNull();
  expect(document.querySelector('input')).toBeNull();expect(page.button(messages.common.retry)).toBeUndefined();
 }finally{await page.close();}
});


test.each(["action","refresh"] as const)("an invitation %s refusal clears the parent access list and its open recipient draft",async failure=>{
 let reads=0;
 globalThis.fetch=async(_url,init)=>{
  if(init?.method==="POST"){
   if(failure==="action")return denied(404);
   const recipient=JSON.parse(String(init.body)).recipients[0];
   return Response.json({results:[{command_key:recipient.command_key,email:recipient.email,invite_id:"new-invite",state:"pending",delivery:"uncertain",code:null}]});
  }
  return ++reads===1?Response.json(access):denied();
 };
 const page=await mount("access");
 try{
  await page.click(page.button(messages.workspace_setup_preview.invite));await page.type('input[type="email"]',"draft@example.test");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]'));
  await page.settle(()=>page.host.textContent?.includes(messages.business.lifecycle.errors.business_unavailable)===true);
  expect(document.body.textContent).not.toContain(member.email);expect(document.querySelector('input')).toBeNull();expect(document.querySelector('[data-testid="side-drawer"]')).toBeNull();
 }finally{await page.close();}
});

test("profile refusal aborts pending images and clears only that Business appearance",async()=>{
 const {publishBusinessAppearance,businessAppearanceSnapshot}=await import("../lib/business-profile-api");
 const other="other-business";
 await publishBusinessAppearance({...profile,appearance:{kind:"avatar",token:"teal",mark:"initials"}} as Parameters<typeof publishBusinessAppearance>[0]);
 await publishBusinessAppearance({...profile,space_id:other,appearance:{kind:"avatar",token:"plum",mark:"icon"}} as Parameters<typeof publishBusinessAppearance>[0]);
 const signals:AbortSignal[]=[];
 globalThis.fetch=async(url,init)=>{
  if(String(url).includes("/assets/"))return new Promise((_resolve,reject)=>{const signal=init?.signal;if(!signal)throw new Error("Image read needs a signal");signals.push(signal);signal.addEventListener("abort",()=>reject(new DOMException("Aborted","AbortError")),{once:true});});
  if(init?.method==="PATCH")return denied(404);
  return Response.json(String(url).endsWith("/fiscal-profile")?fiscal:{...profile,revision:2,appearance:{kind:"image",asset_id:"pending-image",crop:{mode:"fit",zoom:1,x:0,y:0}},image:{asset_id:"pending-image",width:64,height:32,source_url:null,rendered_url:"http://127.0.0.1:4412/assets/pending"}});
 };
 const page=await mount("profile");
 try{
  expect(signals.length).toBeGreaterThan(0);
  await page.click(page.button("Location and contact"));await page.type("profile-address","Attempted private edit");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]'));
  await page.settle(()=>businessAppearanceSnapshot(id)===null);
  expect(signals.every(signal=>signal.aborted)).toBe(true);expect(businessAppearanceSnapshot(other)).toEqual({kind:"avatar",token:"plum",mark:"icon"});expect(document.querySelector('input')).toBeNull();
 }finally{await page.close();}
});


test("a transient profile save failure retains the attempted edit and accepted contact facts",async()=>{
 globalThis.fetch=async(url,init)=>init?.method==="PATCH"?unavailable():Response.json(String(url).endsWith("/fiscal-profile")?fiscal:profile);
 const page=await mount("profile");
 try{
  await page.click(page.button("Location and contact"));await page.type("profile-address","Attempted private edit");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]'));
  await page.settle(()=>document.querySelector('[role="alert"]')!==null);
  expect(document.querySelector<HTMLInputElement>('[name="profile-address"]')?.value).toBe("Attempted private edit");expect(page.host.textContent).toContain("Private address");expect(page.host.textContent).not.toContain(messages.business.lifecycle.errors.business_unavailable);
 }finally{await page.close();}
});
