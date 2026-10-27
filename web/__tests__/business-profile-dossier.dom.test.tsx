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

async function mount(locale="es-419",live=false) {
  const {default:Profile}=await import("../app/design-workspace/BusinessProfilePreview");
  const {BusinessContext}=await import("../components/business-app/BusinessWorkspace");
  const {createFixtureBusinessDataSource}=await import("../components/business-app/fixture-data");
  const messages=locale === "en" ? (await import("../public/locales/en/common.json")).default : (await import("../public/locales/es-419/common.json")).default;
  const i18n=i18next.createInstance();await i18n.init({lng:locale,resources:{[locale]:{translation:messages}}});
  const fixture=createFixtureBusinessDataSource({chatAvailable:true});
  const context={source:live?{...fixture,mode:"live"}:fixture,chosen:{space_id:live?"55555555-5555-4555-8555-555555555555":"profile-test",name:"La Palma",role:"owner",permissions:live?["read","manage"]:undefined},records:{workspace:{country:"DO"}},reload:()=>{},actions:{create:[]}} as unknown as BusinessContextValue;
  const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
  await act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Profile/></BusinessContext.Provider></I18nextProvider>));
  const button=(text:string,container:ParentNode=host)=>[...container.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent?.includes(text))!;
  const click=(element:HTMLElement)=>act(async()=>element.click());
  const type=(name:string,value:string)=>act(async()=>{const field=document.querySelector<HTMLInputElement>(`[name="${name}"]`)!;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field,value);field.dispatchEvent(new Event("input",{bubbles:true}));});
  return {host,button,click,type,close:()=>act(async()=>root.unmount())};
}

test("a saved image must finish loading before editing and its read stops on unmount",async()=>{
 const previousFetch=globalThis.fetch,previousAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;
 process.env.NEXT_PUBLIC_MOCK_AUTH="true";
 const signals:AbortSignal[]=[];
 globalThis.fetch=async(url,init)=>{
  if(String(url).includes("/assets/"))return new Promise((_resolve,reject)=>{const signal=init?.signal;if(!signal)throw new Error("Asset read needs an abort signal");signals.push(signal);signal.addEventListener("abort",()=>reject(new DOMException("Aborted","AbortError")),{once:true});});
  if(String(url).endsWith("/profile"))return Response.json({space_id:"55555555-5555-4555-8555-555555555555",name:"La Palma",country:"DO",currency:"DOP",revision:1,details:{},appearance:{kind:"image",asset_id:"profile-image",crop:{mode:"fit",zoom:1,x:0,y:0}},image:{asset_id:"profile-image",width:64,height:32,source_url:"http://127.0.0.1:4412/assets/source",rendered_url:"http://127.0.0.1:4412/assets/rendered"}});
  return Response.json({name:"La Palma",tax_id:null,can_edit:true});
 };
 const page=await mount("en",true);
 try{expect(signals.length).toBeGreaterThan(0);expect(page.button("Change image").disabled).toBe(true);}
 finally{await page.close();expect(signals.every(signal=>signal.aborted)).toBe(true);globalThis.fetch=previousFetch;if(previousAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=previousAuth;}
});

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

test("identity marks its required field, validates on submit and confirms a successful save",async()=>{
  const page=await mount();try{
    await page.click(page.button("Identidad y datos fiscales"));
    const name=document.querySelector<HTMLInputElement>('[name="business-name"]')!;
    const number=document.querySelector<HTMLInputElement>('[name="tax-id-value"]')!;
    expect(name.required).toBe(true);expect(name.getAttribute("aria-required")).toBe("true");expect(name.placeholder).toContain("Ej.");expect(number.required).toBe(false);expect(number.inputMode).toBe("numeric");expect(number.type).toBe("text");expect(number.placeholder).toBe("Ej. 131-23456-7");
    await page.type("business-name","");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]')!);
    expect(name.getAttribute("aria-invalid")).toBe("true");expect(document.querySelector('[data-testid="form-error-summary"]')).not.toBeNull();
    await page.type("business-name","La Palma actualizada");expect(name.getAttribute("aria-invalid")).toBeNull();
    await page.type("tax-id-value","123");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]')!);expect(number.getAttribute("aria-invalid")).toBe("true");
    await page.type("tax-id-value","");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]')!);
    expect(document.querySelector('[data-footer-slot] [role="status"]')?.textContent).toBe("Datos guardados.");
    await page.type("business-name","Another draft");expect(document.querySelector('[data-footer-slot] [role="status"]')?.textContent).toBe("");
  }finally{await page.close();}
});


test.each([["es-419","Ver perfil","Todavía no hay datos de contacto guardados."],["en","View profile","No contact details have been saved yet."]])("%s opens the saved profile card and returns focus to its action",async(locale,label,emptyHint)=>{
  const page=await mount(locale);try{
    const trigger=page.button(label);await page.click(trigger);
    const card=document.querySelector('[data-testid="business-profile-card"]')!;
    expect(card.textContent).toContain("La Palma");expect(card.textContent).toContain(emptyHint);expect(card.querySelector("input,button,a")).toBeNull();expect(card.querySelector("img")).toBeNull();expect(document.querySelector("[data-footer-slot]")).toBeNull();
    expect(page.host.querySelector("#profile-next-title")).toBeNull();expect(document.querySelectorAll('[data-testid="side-drawer"]')).toHaveLength(1);
    await page.click(document.querySelector<HTMLButtonElement>('[data-testid="side-drawer"] button[aria-label]')!);
    await act(async()=>new Promise(resolve=>requestAnimationFrame(resolve)));expect(document.activeElement).toBe(trigger);expect(page.host.querySelector("#profile-next-title")).not.toBeNull();
  }finally{await page.close();}
});

test("profile card displays saved contact details after an unsaved edit is discarded",async()=>{
  const page=await mount();try{
    await page.click(page.button("Ubicación y contacto"));await page.type("profile-email","saved@example.com");await page.click(document.querySelector<HTMLButtonElement>('button[type="submit"]')!);
    await page.type("profile-email","draft@example.com");await page.click(page.button("Ver perfil"));expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
    await page.click(document.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]')!);
    const card=document.querySelector('[data-testid="business-profile-card"]')!;expect(card.textContent).toContain("saved@example.com");expect(card.textContent).not.toContain("draft@example.com");expect(card.querySelectorAll("dt")).toHaveLength(1);expect(card.querySelector("input")).toBeNull();
  }finally{await page.close();}
});


test.each([["es-419","Ubicación y contacto","Guardar cambios"],["en","Location and contact","Save changes"]])("%s pinned footer submits its associated form without losing invalid drafts",async(locale,section,saveLabel)=>{
  const page=await mount(locale);try{
    await page.click(page.button(section));
    const footer=document.querySelector('[data-footer-slot]')!;
    const save=footer.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    const email=document.querySelector<HTMLInputElement>('[name="profile-email"]')!;
    const live=footer.querySelector('[role="status"]');
    expect(save.textContent).toBe(saveLabel);expect(save.form).toBe(email.form);expect(email.form?.contains(save)).toBe(false);expect(save.disabled).toBe(true);
    await page.type("profile-email","invalid-email");expect(save.disabled).toBe(false);await page.click(save);
    expect(email.value).toBe("invalid-email");expect(email.getAttribute("aria-invalid")).toBe("true");expect(document.querySelector('[data-testid="form-error-summary"]')).not.toBeNull();
    await page.type("profile-email","team@example.com");await page.click(save);
    expect(page.button(section).textContent).toContain("team@example.com");expect(footer.querySelector('[role="status"]')).toBe(live);expect(live?.textContent).not.toBe("");expect(save.disabled).toBe(true);
  }finally{await page.close();}
});
