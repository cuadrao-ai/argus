import {afterAll,afterEach,beforeAll,expect,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import type {BusinessContextValue} from "../components/business-app/BusinessWorkspace";

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz",settings:{navigation:{disableChildFrameNavigation:true}}});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{document.body.innerHTML="";window.localStorage.clear();});
afterAll(async()=>{await GlobalRegistrator.unregister();});

async function mount(locale="es-419") {
  const {default:Profile}=await import("../app/design-workspace/BusinessProfilePreview");
  const {BusinessContext}=await import("../components/business-app/BusinessWorkspace");
  const {createFixtureBusinessDataSource}=await import("../components/business-app/fixture-data");
  const messages=locale === "en" ? (await import("../public/locales/en/common.json")).default : (await import("../public/locales/es-419/common.json")).default;
  const i18n=i18next.createInstance();await i18n.init({lng:locale,resources:{[locale]:{translation:messages}}});
  const context={source:createFixtureBusinessDataSource({chatAvailable:true}),chosen:{space_id:"profile-test",name:"La Palma",role:"owner"},records:{workspace:{country:"DO"}},reload:()=>{},actions:{create:[]}} as unknown as BusinessContextValue;
  const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
  await act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Profile/></BusinessContext.Provider></I18nextProvider>));
  const button=(text:string,container:ParentNode=host)=>[...container.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent?.includes(text))!;
  const click=(element:HTMLElement)=>act(async()=>element.click());
  const type=(name:string,value:string)=>act(async()=>{const field=document.querySelector<HTMLInputElement>(`[name="${name}"]`)!;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field,value);field.dispatchEvent(new Event("input",{bubbles:true}));});
  return {host,button,click,type,close:()=>act(async()=>root.unmount())};
}

test("overview opens the shared non-modal right dossier, hides the checklist and restores it on close",async()=>{
  const page=await mount();try{
    expect(page.host.querySelector("input")).toBeNull();expect(page.host.textContent).toContain("Completa tu perfil");
    const opener=page.button("Identidad y datos fiscales");await page.click(page.host.querySelector<HTMLButtonElement>('[data-profile-checklist="name"]')!);
    expect(document.querySelector('[name="business-name"]')).not.toBeNull();expect(page.host.querySelector("#profile-next-title")).toBeNull();expect(opener.getAttribute("aria-expanded")).toBe("true");
    expect(document.querySelectorAll("#profile-section-dossier")).toHaveLength(1);
    const drawer=document.querySelector('[data-testid="side-drawer"]')!;expect(drawer.getAttribute("role")).toBe("region");expect(drawer.getAttribute("aria-modal")).toBeNull();
    expect(drawer.querySelector("#profile-section-dossier")).not.toBeNull();expect(page.host.querySelector("#profile-section-dossier")).toBeNull();
    expect(document.documentElement.style.getPropertyValue("--cuadrao-drawer-space")).not.toBe("");
    await page.click(document.querySelector<HTMLButtonElement>('[aria-label="Cerrar"]')!);
    expect(page.host.querySelector("#profile-next-title")).not.toBeNull();expect(page.host.querySelector("input")).toBeNull();
    await act(async()=>new Promise(resolve=>requestAnimationFrame(resolve)));expect(document.activeElement).toBe(page.host.querySelector('[data-profile-checklist="name"]'));
  }finally{await page.close();}
});

test("changing sections asks before discarding drafts and summaries use saved contact facts",async()=>{
  const page=await mount();try{
    await page.click(page.button("Ubicación y contacto"));await page.type("profile-address","Calle Sol 10");
    expect(page.button("Ubicación y contacto").textContent).not.toContain("Calle Sol 10");
    await page.click(page.button("Presencia del negocio"));expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
    await page.click(page.button("Seguir editando",document));expect(document.querySelector<HTMLInputElement>('[name="profile-address"]')?.value).toBe("Calle Sol 10");
    await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]')!);expect(page.button("Ubicación y contacto").textContent).toContain("Calle Sol 10");
    await page.click(page.button("Presencia del negocio"));expect(document.querySelector('[role="alertdialog"]')).toBeNull();expect(document.querySelector('[name="profile-address"]')).toBeNull();expect(document.querySelector('[name="profile-website"]')).not.toBeNull();
    await page.type("profile-website","lapalma.do");await page.click(page.button("Identidad y datos fiscales"));await page.click(document.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]')!);
    expect(document.querySelector('[name="business-name"]')).not.toBeNull();expect(page.button("Presencia del negocio").textContent).not.toContain("lapalma.do");
  }finally{await page.close();}
});

test("identity edits protect closing and invoicing reuses the same single right dossier",async()=>{
  const page=await mount("en");try{
    await page.click(page.button("Identity and tax details"));await page.type("business-name","Draft name");
    await page.click(document.querySelector<HTMLButtonElement>('[aria-label="Close"]')!);expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
    await page.click(document.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]')!);expect(page.host.querySelector("#profile-next-title")).not.toBeNull();
    await page.click(page.button("Electronic invoicing"));expect(document.querySelector('iframe[src*="surface=invoicing"][src*="entry=profile"]')).not.toBeNull();expect(document.querySelectorAll('[data-testid="side-drawer"]')).toHaveLength(1);
  }finally{await page.close();}
});
