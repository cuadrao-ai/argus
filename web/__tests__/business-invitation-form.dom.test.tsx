import {afterAll,beforeAll,expect,test,mock} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
mock.module("next/navigation",()=>({useSearchParams:()=>new URLSearchParams(),usePathname:()=>"/biz",useRouter:()=>({push:()=>{},replace:()=>{}})}));

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz"});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterAll(()=>GlobalRegistrator.unregister());
test("an accepted command replay renders its accepted server outcome",async()=>{
 const {BusinessWorkspaceProvider}=await import("@/components/business-app/BusinessWorkspace");
 const {BusinessConsentTestProvider}=await import("@/components/business-app/business-consent-context");
 const {createFixtureBusinessDataSource}=await import("@/components/business-app/fixture-data");
 const {default:Form}=await import("@/components/business-app/BusinessInvitationForm");
 const copy=(await import("@/public/locales/en/common.json")).default;
 const i18n=i18next.createInstance();await i18n.init({lng:"en",resources:{en:{translation:copy}}});
 const originalFetch=globalThis.fetch,originalAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 globalThis.fetch=async(_url,init)=>{const body=JSON.parse(String(init?.body));const recipient=body.recipients[0];return Response.json({results:[{command_key:recipient.command_key,email:recipient.email,invite_id:"accepted-invite",state:"accepted",delivery:null,code:null}]});};
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
 try{
  await act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={createFixtureBusinessDataSource({chatAvailable:false})} userId="mock-auth-user"><Form onClose={()=>{}} onAccepted={()=>{}}/></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>));
  const email=document.querySelector<HTMLInputElement>('input[type="email"]')!;
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(email,"member@example.test");email.dispatchEvent(new Event("input",{bubbles:true}));});
  await act(async()=>document.querySelector("form")!.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})));
  expect(document.body.textContent).toContain("Invitation accepted. Check your access to the business.");
  expect(document.body.textContent).not.toContain("Editor");
  expect(document.body.textContent).not.toContain("Couldn't send");
 }finally{await act(async()=>root.unmount());host.remove();globalThis.fetch=originalFetch;if(originalAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=originalAuth;}
});
