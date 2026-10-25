import {afterAll,afterEach,beforeAll,expect,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import type {BusinessContextValue} from "../components/business-app/BusinessWorkspace";

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz"});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{document.body.innerHTML="";window.localStorage.clear();});
afterAll(async()=>{await GlobalRegistrator.unregister();});
async function mount() {
  const {default:Reading}=await import("../app/design-workspace/ReceiptReadingPreview");
  const {BusinessContext}=await import("../components/business-app/BusinessWorkspace");
  const {BusinessConsentTestProvider}=await import("../components/business-app/business-consent-context");
  const messages=(await import("../public/locales/es-419/common.json")).default;
  const i18n=i18next.createInstance();await i18n.init({lng:"es-419",resources:{"es-419":{translation:messages}}});
  const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
  let networkCalls=0;
  const render=(businessId:string,accepted=true,role="owner")=>act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted={accepted}><BusinessContext.Provider value={{chosen:{space_id:businessId,role},source:{setReceiptReading:()=>{networkCalls++;throw new Error("network_must_not_run");}}} as unknown as BusinessContextValue}><Reading key={businessId}/></BusinessContext.Provider></BusinessConsentTestProvider></I18nextProvider>));
  return {host,render,toggle:()=>host.querySelector<HTMLButtonElement>('[role="switch"]'),networkCalls:()=>networkCalls,close:()=>act(async()=>root.unmount())};
}
test("mock reading starts off, persists by business and never calls the API",async()=>{
  const page=await mount();try {
    await page.render("palma");expect(page.toggle()?.getAttribute("aria-checked")).toBe("false");
    await act(async()=>page.toggle()!.click());expect(page.toggle()?.getAttribute("aria-checked")).toBe("true");
    await page.render("luna");expect(page.toggle()?.getAttribute("aria-checked")).toBe("false");
    await page.render("palma");expect(page.toggle()?.getAttribute("aria-checked")).toBe("true");
    await act(async()=>page.toggle()!.click());expect(page.toggle()?.getAttribute("aria-checked")).toBe("false");
    expect(page.networkCalls()).toBe(0);
  }finally{await page.close();}
});
test("mock reading respects consent and member change restrictions",async()=>{
  const page=await mount();try {
    await page.render("palma",false);expect(page.toggle()).toBeNull();expect(page.host.textContent).toContain("No disponible");
    await page.render("palma",true,"accountant");expect(page.toggle()?.disabled).toBe(true);
    await act(async()=>page.toggle()!.click());expect(page.toggle()?.getAttribute("aria-checked")).toBe("false");expect(page.networkCalls()).toBe(0);
  }finally{await page.close();}
});
