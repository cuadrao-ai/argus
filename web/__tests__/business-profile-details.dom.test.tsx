import {afterAll,afterEach,beforeAll,expect,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import {normalizeBusinessProvidedDetails,type BusinessProvidedDetails} from "../app/design-workspace/businessProfilePreviewState";

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz"});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{document.body.innerHTML="";});
afterAll(async()=>{await GlobalRegistrator.unregister();});
async function mount(fails=false,locale="es-419"){
 const {default:BusinessProfileDetails}=await import("../app/design-workspace/BusinessProfileDetails");
 const messages=locale==="en" ? (await import("../public/locales/en/common.json")).default : (await import("../public/locales/es-419/common.json")).default;
 const i18n=i18next.createInstance();await i18n.init({lng:locale,resources:{[locale]:{translation:messages}}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);const writes:BusinessProvidedDetails[]=[];
 const render=(saved=normalizeBusinessProvidedDetails({}))=>act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessProfileDetails saved={saved} canEdit onSave={details=>{if(fails)throw new Error("quota");const next=normalizeBusinessProvidedDetails(details);writes.push(next);return next;}}/></I18nextProvider>));
 await render();
 const field=(name:string)=>host.querySelector<HTMLInputElement>(`[name="profile-${name}"]`)!;
 const type=(name:string,value:string)=>act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field(name),value);field(name).dispatchEvent(new Event("input",{bubbles:true}));});
 const blur=(name:string)=>act(async()=>{field(name).focus();field(name).blur();});
 const save=()=>act(async()=>host.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
 return {host,writes,field,type,blur,save,render,close:()=>act(async()=>root.unmount())};
}
test("optional invalid fields show blur errors and linked submit summary, then normalize valid website",async()=>{
 const form=await mount();try{
  await form.type("email","invalid");expect(form.field("email").getAttribute("aria-invalid")).toBeNull();await form.blur("email");expect(form.field("email").getAttribute("aria-invalid")).toBe("true");
  await form.type("website","javascript:alert(1)");await form.save();expect(form.writes).toHaveLength(0);
  const summary=form.host.querySelector('[data-testid="form-error-summary"]')!;expect(summary.querySelectorAll("a")).toHaveLength(2);
  await act(async()=>summary.querySelector<HTMLAnchorElement>("a")!.dispatchEvent(new MouseEvent("click",{bubbles:true,cancelable:true})));expect(document.activeElement).toBe(form.field("email"));
  await form.type("email","");await form.type("website","lapalma.do");await form.save();expect(form.writes).toHaveLength(1);expect(form.writes[0].website).toBe("https://lapalma.do");expect(form.field("website").value).toBe("https://lapalma.do");expect(form.host.textContent).toContain("Datos guardados.");
 }finally{await form.close();}
});
test("a failed save keeps the draft and announces failure without success",async()=>{
 const form=await mount(true,"en");try{await form.type("address","Calle Sol 10");await form.save();expect(form.field("address").value).toBe("Calle Sol 10");expect(form.host.textContent).toContain("We couldn't save these details.");expect(form.host.textContent).not.toContain("Details saved.");expect(form.writes).toHaveLength(0);}finally{await form.close();}
});
test("unrelated saved-state updates do not discard a contact draft",async()=>{
 const form=await mount();try{await form.type("address","Unfinished address");await form.render(normalizeBusinessProvidedDetails({phone:"809 555 0100"}));expect(form.field("address").value).toBe("Unfinished address");expect(form.field("phone").value).toBe("");}finally{await form.close();}
});

test.each([
 ["es-419","Formato de correo válido.","Formato de sitio web válido."],
 ["en","Valid email format.","Valid website format."],
])("%s optional fields use examples and only show format success after a check",async(locale,emailMessage,websiteMessage)=>{
 const form=await mount(false,locale);try{
  for(const field of ["address","province","municipality","email","phone","website","description"]){expect(form.field(field).placeholder.length).toBeGreaterThan(0);expect(form.field(field).required).toBe(false);}
  const note=(name:string)=>document.getElementById(`${form.field(name).id}-note`);
  await form.type("email","hello@example.com");expect(note("email")?.textContent).toBe("");await form.blur("email");expect(note("email")?.textContent).toBe(emailMessage);expect(form.field("email").getAttribute("aria-describedby")).toBe(note("email")?.id ?? null);
  await form.type("email","next@example.com");expect(note("email")?.textContent).toBe("");await form.blur("email");expect(note("email")?.textContent).toBe(emailMessage);
  await form.type("website","example.com");expect(note("website")?.textContent).toBe("");await form.blur("website");expect(note("website")?.textContent).toBe(websiteMessage);
  await form.type("website","");expect(note("website")?.textContent).toBe("");expect(form.field("website").getAttribute("aria-invalid")).toBeNull();
  await form.type("address","Calle Sol 10");await form.blur("address");expect(note("address")).toBeNull();
 }finally{await form.close();}
});
