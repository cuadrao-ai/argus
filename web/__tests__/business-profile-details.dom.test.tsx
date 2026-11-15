import {afterAll,afterEach,beforeAll,expect,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import {normalizeBusinessProvidedDetails,type BusinessProvidedDetails} from "../app/design-workspace/businessProfilePreviewState";
import spanish from "../public/locales/es-419/common.json";
import english from "../public/locales/en/common.json";

const i18nText=(locale:string,key:string)=>((locale==="en"?english:spanish).business.settings as Record<string,string>)[key];

beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz"});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;});
afterEach(()=>{document.body.innerHTML="";});
afterAll(async()=>{await GlobalRegistrator.unregister();});
type Refused=Partial<Record<keyof BusinessProvidedDetails,string>>;
/** A stand-in for the server: the test names which values it refuses, with which code, and the saved form of the ones it accepts. */
const serverRefusing=(refusals:Record<string,string>,forms:Record<string,string>)=>{
 const asked:Partial<BusinessProvidedDetails>[]=[];
 const refusedOf=(typed:Partial<BusinessProvidedDetails>):Refused=>Object.fromEntries(Object.entries(typed).filter(([,value])=>refusals[value]).map(([field,value])=>[field,refusals[value]]));
 return {asked,refusedOf,check:async(typed:Partial<BusinessProvidedDetails>)=>{asked.push(typed);const refused=refusedOf(typed);return {refused,savedForm:Object.keys(refused).length?{}:Object.fromEntries(Object.entries(typed).map(([field,value])=>[field,forms[value]??value]))};}};
};
const settle=(ms=5)=>act(async()=>{await new Promise(resolve=>setTimeout(resolve,ms));});
async function mount({locale="es-419",refusals,forms={},saved={},fails=false,closes=false}:{locale?:string;refusals?:Record<string,string>;forms?:Record<string,string>;saved?:Partial<BusinessProvidedDetails>;fails?:boolean;closes?:boolean}={}){
 const {default:BusinessProfileDetails}=await import("../app/design-workspace/BusinessProfileDetails");
 const messages=locale==="en" ? (await import("../public/locales/en/common.json")).default : (await import("../public/locales/es-419/common.json")).default;
 const i18n=i18next.createInstance();await i18n.init({lng:locale,resources:{[locale]:{translation:messages}}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);const writes:BusinessProvidedDetails[]=[];
 const server=refusals?serverRefusing(refusals,forms):null;let closed=0;
 const onSave=(details:BusinessProvidedDetails)=>{
  if(fails)throw new Error("quota");
  const refused=server?.refusedOf(details)??{};
  if(Object.keys(refused).length)throw Object.assign(new Error("refused"),{status:422,code:"invalid_business_details",fieldErrors:refused});
  const next=normalizeBusinessProvidedDetails(details);writes.push(next);return next;
 };
 const render=(saved=normalizeBusinessProvidedDetails({}))=>act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessProfileDetails saved={saved} canEdit onCheck={server?.check} onSaved={closes?()=>{closed+=1;}:undefined} onSave={onSave}/></I18nextProvider>));
 await render(normalizeBusinessProvidedDetails(saved));
 const field=(name:string)=>host.querySelector<HTMLInputElement>(`[name="profile-${name}"]`)!;
 const note=(name:string)=>document.getElementById(`${field(name).id}-note`)?.textContent;
 const type=(name:string,value:string)=>act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field(name),value);field(name).dispatchEvent(new Event("input",{bubbles:true}));});
 const blur=async(name:string)=>{await act(async()=>{field(name).focus();field(name).blur();});await settle();};
 const save=()=>act(async()=>host.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
 return {host,writes,server,field,note,type,blur,save,render,closed:()=>closed,close:()=>act(async()=>root.unmount())};
}
test("the form holds no email, website or phone rule: without a server answer it refuses nothing",async()=>{
 const form=await mount();try{
  await form.type("email","invalid");await form.blur("email");await form.type("website","javascript:alert(1)");await form.blur("website");await form.type("phone","abc 12");await form.blur("phone");
  for(const name of ["email","website","phone"])expect(form.field(name).getAttribute("aria-invalid")).toBeNull();
  await form.save();expect(form.host.querySelector('[data-testid="form-error-summary"]')).toBeNull();
  expect(form.writes).toEqual([normalizeBusinessProvidedDetails({email:"invalid",website:"javascript:alert(1)",phone:"abc 12"})]);
 }finally{await form.close();}
});
test("a field that is left shows the server's answer, then is asked again while it is being fixed",async()=>{
 const form=await mount({refusals:{"abc 12":"invalid_business_phone_length","abc 123":"invalid_business_phone_length"}});try{
  await form.type("phone","abc 12");expect(form.server!.asked).toEqual([]);expect(form.field("phone").getAttribute("aria-invalid")).toBeNull();
  await form.blur("phone");expect(form.server!.asked).toEqual([{phone:"abc 12"}]);
  expect(form.field("phone").getAttribute("aria-invalid")).toBe("true");expect(form.note("phone")).toBe("Escribe los 10 dígitos de tu número, incluido el código de área.");
  await form.type("phone","abc 123");await settle(340);expect(form.field("phone").getAttribute("aria-invalid")).toBe("true");
  await form.type("phone","809-555-0142");await settle(340);
  expect(form.server!.asked.at(-1)).toEqual({phone:"809-555-0142"});expect(form.field("phone").getAttribute("aria-invalid")).toBeNull();expect(form.note("phone")).toBe(i18nText("es-419","profile_format_phone_placeholder"));
 }finally{await form.close();}
});
const SERVER_FORMS={"8095550142":"+1 809 555 0142","(809) 555-0142":"+1 809 555 0142","example.com":"https://example.com"};
test("a valid phone that is left shows the server's form; typing asks nothing and no other field is rewritten",async()=>{
 const form=await mount({refusals:{},forms:SERVER_FORMS});try{
  await form.type("phone","8095550142");expect(form.server!.asked).toEqual([]);expect(form.field("phone").value).toBe("8095550142");
  await form.blur("phone");expect(form.server!.asked).toEqual([{phone:"8095550142"}]);
  expect(form.field("phone").value).toBe("+1 809 555 0142");expect(form.note("phone")).toBe(i18nText("es-419","profile_format_phone_placeholder"));
  await form.blur("phone");expect(form.server!.asked).toHaveLength(1);
  await form.type("website","example.com");await form.blur("website");expect(form.field("website").value).toBe("example.com");
  await form.save();expect(form.writes.at(-1)!.phone).toBe("+1 809 555 0142");
 }finally{await form.close();}
});
test("a phone typed in another shape than the saved one goes back to the saved form when left, with nothing to save",async()=>{
 const form=await mount({refusals:{},forms:SERVER_FORMS,saved:{phone:"+1 809 555 0142"}});try{
  const save=form.host.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  await form.type("phone","(809) 555-0142");expect(save.disabled).toBe(false);
  await form.blur("phone");expect(form.field("phone").value).toBe("+1 809 555 0142");expect(save.disabled).toBe(true);
 }finally{await form.close();}
});
test("a phone fixed after an error keeps what is typed until the field is left, then shows the server's form without asking again",async()=>{
 const form=await mount({refusals:{"809555":"invalid_business_phone_length"},forms:SERVER_FORMS});try{
  await form.type("phone","809555");await form.blur("phone");expect(form.field("phone").getAttribute("aria-invalid")).toBe("true");
  await form.type("phone","8095550142");await settle(340);
  expect(form.field("phone").getAttribute("aria-invalid")).toBeNull();expect(form.field("phone").value).toBe("8095550142");
  const asked=form.server!.asked.length;await form.blur("phone");
  expect(form.field("phone").value).toBe("+1 809 555 0142");expect(form.server!.asked).toHaveLength(asked);
 }finally{await form.close();}
});
test("a late answer does not overwrite what was typed after the field was left",async()=>{
 const form=await mount({refusals:{},forms:SERVER_FORMS});try{
  await form.type("phone","8095550142");
  await act(async()=>{form.field("phone").focus();form.field("phone").blur();});
  await form.type("phone","80955501");await settle();
  expect(form.field("phone").value).toBe("80955501");
 }finally{await form.close();}
});
test.each([
 ["es-419","abc","empty","Escribe tu número de teléfono."],
 ["es-419","809-555-014","length","Escribe los 10 dígitos de tu número, incluido el código de área."],
 ["es-419","809-155-0142","format","Revisa el código de área y los demás dígitos de tu número."],
 ["es-419","+44 20 7946 0958","region","Usa un número de República Dominicana o Estados Unidos."],
 ["en","abc","empty","Enter your phone number."],
 ["en","809-555-014","length","Enter all 10 digits of your number, including the area code."],
 ["en","809-155-0142","format","Check the area code and the remaining digits of your number."],
 ["en","+44 20 7946 0958","region","Use a number from the Dominican Republic or the United States."],
])("%s phone %s refused for %s shows that reason's message",async(locale,typed,reason,message)=>{
 const form=await mount({locale,refusals:{[typed]:`invalid_business_phone_${reason}`}});try{
  await form.type("phone",typed);await form.blur("phone");
  expect(form.field("phone").getAttribute("aria-invalid")).toBe("true");expect(form.note("phone")).toBe(message);
 }finally{await form.close();}
});
test("a refused save shows the server's error under each field, lists them, focuses the first and stays open",async()=>{
 const form=await mount({closes:true,refusals:{"a@host":"invalid_business_email","abc 12":"invalid_business_phone_length"}});try{
  await form.type("address","Calle Sol 10");await form.type("email","a@host");await form.type("phone","abc 12");await form.save();
  expect(form.writes).toHaveLength(0);expect(form.closed()).toBe(0);
  expect(form.note("email")).toBe("Escribe un correo electrónico válido.");expect(form.note("phone")).toBe("Escribe los 10 dígitos de tu número, incluido el código de área.");
  const summary=form.host.querySelector('[data-testid="form-error-summary"]')!;expect([...summary.querySelectorAll("a")].map(link=>link.textContent)).toEqual(["Correo del negocio","Teléfono o WhatsApp"]);
  await act(async()=>new Promise(resolve=>requestAnimationFrame(resolve)));expect(document.activeElement).toBe(form.field("email"));expect(form.field("address").value).toBe("Calle Sol 10");
  await form.type("email","hola@ejemplo.com");await form.type("phone","809-555-0142");await settle(340);await form.save();
  expect(form.writes).toHaveLength(1);expect(form.closed()).toBe(1);
 }finally{await form.close();}
});
test("a successful save closes through its owner and shows no inline confirmation; alone it confirms inline",async()=>{
 const closing=await mount({closes:true});try{await closing.type("address","Calle Sol 10");await closing.save();expect(closing.closed()).toBe(1);expect(closing.host.textContent).not.toContain("Datos guardados.");}finally{await closing.close();}
 const alone=await mount();try{await alone.type("address","Calle Sol 10");await alone.save();expect(alone.host.textContent).toContain("Datos guardados.");}finally{await alone.close();}
});
test("a failed save keeps the draft, stays open and announces failure without success",async()=>{
 const form=await mount({fails:true,closes:true,locale:"en"});try{await form.type("address","Calle Sol 10");await form.save();expect(form.field("address").value).toBe("Calle Sol 10");expect(form.host.textContent).toContain("We couldn't save these details.");expect(form.host.textContent).not.toContain("Details saved.");expect(form.writes).toHaveLength(0);expect(form.closed()).toBe(0);}finally{await form.close();}
});
test("an asynchronous server refusal keeps attempted edits and never confirms a save",async()=>{
 const {default:BusinessProfileDetails}=await import("../app/design-workspace/BusinessProfileDetails");
 const messages=(await import("../public/locales/en/common.json")).default;
 const i18n=i18next.createInstance();await i18n.init({lng:"en",resources:{en:{translation:messages}}});
 const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
 let refuse:((reason:Error)=>void)|undefined;
 await act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessProfileDetails saved={normalizeBusinessProvidedDetails({})} canEdit onSave={()=>new Promise<BusinessProvidedDetails>((_resolve,reject)=>{refuse=reject;})}/></I18nextProvider>));
 try {
  const input=host.querySelector<HTMLInputElement>('[name="profile-address"]')!;
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(input,"Calle Luna 12");input.dispatchEvent(new Event("input",{bubbles:true}));});
  await act(async()=>host.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
  expect(host.textContent).not.toContain("Details saved.");
  await act(async()=>{refuse?.(new Error("business_workspace_stale"));});
  expect(input.value).toBe("Calle Luna 12");expect(host.textContent).toContain("We couldn't save these details.");
 } finally {await act(async()=>root.unmount());}
});
test("unrelated saved-state updates do not discard a contact draft",async()=>{
 const form=await mount();try{await form.type("address","Unfinished address");await form.render(normalizeBusinessProvidedDetails({phone:"809 555 0100"}));expect(form.field("address").value).toBe("Unfinished address");expect(form.field("phone").value).toBe("");}finally{await form.close();}
});

test("unrelated saved-state updates do not discard a contact draft",async()=>{
 const form=await mount();try{await form.type("address","Unfinished address");await form.render(normalizeBusinessProvidedDetails({phone:"809 555 0100"}));expect(form.field("address").value).toBe("Unfinished address");expect(form.field("phone").value).toBe("");}finally{await form.close();}
});

test.each([
 ["es-419","Formato de correo válido.","Formato de sitio web válido."],
 ["en","Valid email format.","Valid website format."],
])("%s optional fields use examples and only show format success after the server accepts the value",async(locale,emailMessage,websiteMessage)=>{
 const form=await mount({locale,refusals:{}});try{
  for(const field of ["address","province","municipality","email","phone","website","description"]){expect(form.field(field).placeholder.length).toBeGreaterThan(0);expect(form.field(field).required).toBe(false);}
  await form.type("email","hello@example.com");expect(form.note("email")).toBe("");await form.blur("email");expect(form.note("email")).toBe(emailMessage);expect(form.field("email").getAttribute("aria-describedby")).toBe(`${form.field("email").id}-note`);
  await form.type("email","next@example.com");expect(form.note("email")).toBe("");await form.blur("email");expect(form.note("email")).toBe(emailMessage);
  await form.type("website","example.com");expect(form.note("website")).toBe("");await form.blur("website");expect(form.note("website")).toBe(websiteMessage);
  await form.type("phone","809 555 0142");await form.blur("phone");expect(form.note("phone")).toBe(i18nText(locale,"profile_format_phone_placeholder"));
  await form.type("website","");expect(form.note("website")).toBe("");expect(form.field("website").getAttribute("aria-invalid")).toBeNull();
  await form.type("address","Calle Sol 10");await form.blur("address");expect(document.getElementById(`${form.field("address").id}-note`)).toBeNull();
 }finally{await form.close();}
});
