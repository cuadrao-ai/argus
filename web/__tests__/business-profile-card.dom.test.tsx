import {afterAll,afterEach,beforeAll,expect,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import {readBusinessProfilePreview} from "../app/design-workspace/businessProfilePreviewState";

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz"});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{document.body.innerHTML="";});
afterAll(async()=>{await GlobalRegistrator.unregister();});
async function mount(locale="es-419") {
  const {default:Card}=await import("../app/design-workspace/BusinessProfileCard");
  const messages=locale === "en" ? (await import("../public/locales/en/common.json")).default : (await import("../public/locales/es-419/common.json")).default;
  const i18n=i18next.createInstance();await i18n.init({lng:locale,resources:{[locale]:{translation:messages}}});
  const profile=readBusinessProfilePreview({getItem:()=>JSON.stringify({businessProvidedDetails:{description:"Panadería artesanal",address:"Calle Sol 10",province:"Santiago",municipality:"Santiago de los Caballeros",email:"hello@example.com",phone:"809 555 0100",website:"https://example.com"}}),setItem:()=>{}},"business-card","La Palma","DO");
  const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
  const render=(logoUrl?:string)=>act(async()=>root.render(<I18nextProvider i18n={i18n}><Card profile={profile} logoUrl={logoUrl}/></I18nextProvider>));
  await render();return {host,render,close:()=>act(async()=>root.unmount())};
}

test.each([["es-419","Correo del negocio"],["en","Business email"]])("%s card shows saved identity, description and contacts without editing controls",async(locale,emailLabel)=>{
  const card=await mount(locale);try{
    expect(card.host.querySelector("h3")?.textContent).toBe("La Palma");expect(card.host.textContent).toContain("Panadería artesanal");expect(card.host.textContent).toContain(emailLabel);
    expect([...card.host.querySelectorAll("dd")].map(item=>item.textContent)).toEqual(["Calle Sol 10\nSantiago de los Caballeros, Santiago","hello@example.com","809 555 0100","https://example.com"]);
    expect(card.host.querySelector("form,input,button,a")).toBeNull();expect(card.host.textContent).not.toContain("RNC");
  }finally{await card.close();}
});

test("a saved logo falls back on failure and a new source can load",async()=>{
  const card=await mount();try{
    await card.render("https://example.test/business-logo.png");const image=card.host.querySelector("img")!;expect(image.getAttribute("src")).toBe("https://example.test/business-logo.png");
    await act(async()=>image.dispatchEvent(new Event("error")));expect(card.host.querySelector("img")).toBeNull();expect(card.host.querySelector("svg")).not.toBeNull();
    await card.render("https://example.test/new-logo.png");expect(card.host.querySelector("img")?.getAttribute("src")).toBe("https://example.test/new-logo.png");
    await card.render("javascript:alert(1)");expect(card.host.querySelector("img")).toBeNull();
  }finally{await card.close();}
});
