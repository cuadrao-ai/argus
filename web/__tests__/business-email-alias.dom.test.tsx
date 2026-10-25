import {afterAll,afterEach,beforeAll,expect,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import {invitationStorageKeys} from "../app/design-workspace/businessAccessPreviewState";

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz"});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{document.body.innerHTML="";window.localStorage.clear();});
afterAll(async()=>{await GlobalRegistrator.unregister();});
for(const locale of ["es-419","en"])test(`${locale} suggestions fill and focus only the alias until explicit save`,async()=>{
  const {default:Alias}=await import("../app/design-workspace/BusinessEmailAliasPreview");
  const messages=locale === "en" ? (await import("../public/locales/en/common.json")).default : (await import("../public/locales/es-419/common.json")).default;
  const i18n=i18next.createInstance();await i18n.init({lng:locale,resources:{[locale]:{translation:messages}}});
  const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
  const key=invitationStorageKeys("palma").guide;
  try {
    await act(async()=>root.render(<I18nextProvider i18n={i18n}><Alias businessId="palma" businessName="La Palma" defaultAddress="recibos-123@recibos.cuadrao.example" canEdit/></I18nextProvider>));
    await act(async()=>host.querySelector<HTMLButtonElement>("button")!.click());
    const input=host.querySelector<HTMLInputElement>('input[name="receiving-alias"]')!;
    const group=host.querySelector('[role="group"]')!;
    expect(group.getAttribute("aria-label")).toBe(locale === "en" ? "Suggestions:" : "Sugerencias:");
    expect([...group.querySelectorAll("button")].map(button=>button.textContent)).toEqual(["la-palma","lapalma","la-palma-recibos"]);
    await act(async()=>group.querySelectorAll<HTMLButtonElement>("button")[1].click());
    expect(input.value).toBe("lapalma");expect(document.activeElement).toBe(input);expect(window.localStorage.getItem(key)).toBeNull();
    expect(input.parentElement?.querySelector("svg")).toBeNull();
    const suffix=document.getElementById(`${input.id}-suffix`)!;expect(suffix.textContent).toBe("@recibos.cuadrao.example");expect(input.getAttribute("aria-describedby")).toContain(suffix.id);
    await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")!.set!.call(input,"palma-editado");input.dispatchEvent(new Event("input",{bubbles:true}));});
    expect(window.localStorage.getItem(key)).toBeNull();
    await act(async()=>host.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
    expect(JSON.parse(window.localStorage.getItem(key)!).address).toBe("palma-editado@recibos.cuadrao.example");expect(host.querySelector("input")).toBeNull();
  }finally{await act(async()=>root.unmount());}
});
