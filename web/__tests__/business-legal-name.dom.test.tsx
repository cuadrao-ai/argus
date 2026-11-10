import {afterAll,afterEach,beforeAll,expect,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";
import {act} from "react";
import {createRoot} from "react-dom/client";
import i18next from "i18next";
import {I18nextProvider} from "react-i18next";
import spanish from "../public/locales/es-419/common.json";
import english from "../public/locales/en/common.json";
import type {BusinessContextValue} from "../components/business-app/BusinessWorkspace";
import type {FiscalProfile,RegistryAnswer} from "../lib/business-dgii";

const SPACE="55555555-5555-4555-8555-555555555555";
const LONG_NAME="ASOCIACION DOMINICANA DE PRODUCTORES Y DISTRIBUIDORES DE MATERIALES DE CONSTRUCCION Y FERRETERIA DEL CIBAO ORIENTAL Y LA REGION NORDESTE SRL";
type Call={method:string;path:string;body:unknown;key:string|null};
type Reply=(call:Call)=>Response;

let previousFetch:typeof fetch,previousAuth:string|undefined;
beforeAll(()=>{GlobalRegistrator.register({url:"http://localhost/biz",settings:{navigation:{disableChildFrameNavigation:true}}});(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;previousFetch=globalThis.fetch;previousAuth=process.env.NEXT_PUBLIC_MOCK_AUTH;process.env.NEXT_PUBLIC_MOCK_AUTH="true";});
afterEach(()=>{document.body.innerHTML="";window.localStorage.clear();globalThis.fetch=previousFetch;});
afterAll(async()=>{if(previousAuth===undefined)delete process.env.NEXT_PUBLIC_MOCK_AUTH;else process.env.NEXT_PUBLIC_MOCK_AUTH=previousAuth;await GlobalRegistrator.unregister();});

const answer=(value:string,verification:RegistryAnswer["verification"],name=LONG_NAME,status="ACTIVO"):RegistryAnswer=>({tax_id:{type:"rnc",value},verification,record:verification==="sin_verificar"?null:{rnc:value,name,trade_name:null,status,file_date:"2026-10-20"},checked_at:"2026-11-09T12:00:00Z"});
const failure=(status=500)=>Response.json({code:"internal_error",request_id:"ref-legal-0001"},{status});

/** A live server: the saved profile, the registry answers by number, and every call in order. */
function server(saved:FiscalProfile,registry:(value:string)=>Response,overrides:{patch?:Reply;put?:Reply}={}){
  const calls:Call[]=[];
  let profile=saved;
  globalThis.fetch=(async(url:string|URL|Request,init?:RequestInit)=>{
    const path=new URL(String(url),"http://localhost").pathname.replace(/^.*\/api\/v1/,"");
    const method=init?.method??"GET";
    const body=init?.body?JSON.parse(String(init.body)):null;
    const key=new Headers(init?.headers).get("Idempotency-Key");
    const call={method,path,body,key};
    if(path.endsWith("/profile"))return Response.json({space_id:SPACE,name:"La Palma",country:"DO",currency:"DOP",revision:1,details:{},appearance:{kind:"default"},image:null});
    calls.push(call);
    if(path==="/business/fiscal-profile/registry")return registry(body.tax_id.value);
    if(path==="/business/fiscal-profile"&&method==="PATCH"){
      if(overrides.patch)return overrides.patch(call);
      const changed=JSON.stringify(body.tax_id)!==JSON.stringify(profile.tax_id);
      profile={...profile,name:body.name,tax_id:body.tax_id?{type:body.tax_id.type,value:body.tax_id.value.replace(/[ -]/g,"")}:null,legal_name:changed?null:profile.legal_name};
      return Response.json(profile);
    }
    if(path==="/business/fiscal-profile/legal-name"){
      if(overrides.put)return overrides.put(call);
      profile={...profile,legal_name:{value:body.legal_name,confirmed_at:"2026-11-09T12:00:00Z"}};
      return Response.json(profile);
    }
    return Response.json(profile);
  }) as typeof fetch;
  return calls;
}

const flush=async()=>{for(let index=0;index<6;index+=1)await act(async()=>{await new Promise(resolve=>setTimeout(resolve,0));});};

async function mount(locale:"es-419"|"en"="es-419"){
  const {default:Profile}=await import("../app/design-workspace/BusinessProfilePreview");
  const {BusinessContext}=await import("../components/business-app/BusinessWorkspace");
  const {createFixtureBusinessDataSource}=await import("../components/business-app/fixture-data");
  const {lookupRegistry,setLegalName}=await import("../lib/business-dgii");
  const i18n=i18next.createInstance();await i18n.init({lng:locale,resources:{[locale]:{translation:locale==="en"?english:spanish}}});
  const fixture=createFixtureBusinessDataSource({chatAvailable:true});
  const context={invoicing:"sample" as const,source:{...fixture,mode:"live",lookupRegistry,saveLegalName:setLegalName},chosen:{space_id:SPACE,name:"La Palma",role:"owner",permissions:["read","manage"]},records:{workspace:{country:"DO"}},reload:()=>{},actions:{create:[]}} as unknown as BusinessContextValue;
  const host=document.createElement("div");document.body.append(host);const root=createRoot(host);
  await act(async()=>root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Profile/></BusinessContext.Provider></I18nextProvider>));
  await flush();
  const button=(text:string)=>[...document.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent?.includes(text))!;
  await act(async()=>button(locale==="en"?"Identity and tax details":"Identidad y datos fiscales").click());
  await flush();
  const block=()=>document.querySelector<HTMLElement>('[data-testid="legal-name"]');
  const type=async(value:string)=>{await act(async()=>{const field=document.querySelector<HTMLInputElement>('[name="tax-id-value"]')!;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set?.call(field,value);field.dispatchEvent(new Event("input",{bubbles:true}));});await flush();};
  const save=async()=>{await act(async()=>{document.querySelector<HTMLFormElement>('[data-testid="business-fiscal-profile"] form')!.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}));});await flush();};
  return {block,type,save,button,close:()=>act(async()=>root.unmount())};
}

const empty:FiscalProfile={name:"La Palma",tax_id:null,legal_name:null,can_edit:true};
const writes=(calls:Call[])=>calls.filter(call=>call.method!=="GET"&&call.path!=="/business/fiscal-profile/registry").map(call=>`${call.method} ${call.path}`);

test("Por confirmar shows the registry name, says who it confirms, and saving confirms it after the number",async()=>{
  const calls=server(empty,value=>Response.json(answer(value,"verificado")));
  const page=await mount();
  try{
    await page.type("131-00001-4");
    const block=page.block()!;
    expect(block.dataset.legalNameStatus).toBe("pending");
    expect(block.textContent).toContain("Razón social");expect(block.textContent).toContain("Por confirmar");
    expect(block.textContent).toContain(LONG_NAME);expect(block.textContent).toContain("Según la DGII");
    expect(block.querySelector("input")).toBeNull();
    expect(document.querySelector('[data-testid="legal-name-confirm"]')?.textContent).toBe("Al guardar, confirmas que este RNC corresponde a La Palma.");
    await page.save();
    expect(writes(calls)).toEqual(["PATCH /business/fiscal-profile","PUT /business/fiscal-profile/legal-name"]);
    expect(calls.find(call=>call.method==="PUT")?.body).toEqual({legal_name:LONG_NAME,previous_legal_name:null,tax_id:{type:"rnc",value:"131000014"},confirmed:true});
    expect(page.block()?.dataset.legalNameStatus).toBe("verified");
    expect(page.block()?.textContent).toContain("Verificado");expect(page.block()?.querySelector("svg")).not.toBeNull();
    expect(document.querySelector('[data-testid="legal-name-confirm"]')).toBeNull();
  }finally{await page.close();}
});

test("Verificado comes from the stored legal name for the current number, with no registry call",async()=>{
  const calls=server({...empty,tax_id:{type:"rnc",value:"131000014"},legal_name:{value:"TALLER PALMA SRL",confirmed_at:"2026-11-09T12:00:00Z"}},()=>failure());
  const page=await mount();
  try{
    expect(page.block()?.dataset.legalNameStatus).toBe("verified");
    expect(page.block()?.textContent).toContain("TALLER PALMA SRL");expect(page.block()?.textContent).toContain("Según la DGII");
    expect(calls.some(call=>call.path==="/business/fiscal-profile/registry")).toBe(false);
    // Changing the number clears it and checks the new one.
    await page.type("131000022");
    expect(calls.filter(call=>call.path==="/business/fiscal-profile/registry").map(call=>(call.body as {tax_id:{value:string}}).tax_id.value)).toEqual(["131000022"]);
    expect(page.block()?.dataset.legalNameStatus).toBe("failed");
  }finally{await page.close();}
});

test("Sin verificar shows the tag and a dash only, with no source line, and saving stores the number only",async()=>{
  const calls=server(empty,value=>Response.json(answer(value,"sin_verificar")));
  const page=await mount();
  try{
    await page.type("131000031");
    const block=page.block()!;
    expect(block.dataset.legalNameStatus).toBe("unverified");
    expect(block.textContent).toContain("Sin verificar");
    expect(block.querySelector('[data-testid="legal-name-value"]')).toBeNull();
    expect([...block.querySelectorAll("p")].map(item=>item.textContent)).toEqual(["-"]);
    expect(block.textContent).not.toContain("DGII");
    expect(document.querySelector('[data-testid="legal-name-confirm"]')).toBeNull();
    await page.save();
    expect(writes(calls)).toEqual(["PATCH /business/fiscal-profile"]);
  }finally{await page.close();}
});

test("No activo names the registry status and saving still confirms it",async()=>{
  const calls=server(empty,value=>Response.json(answer(value,"no_activo","FERRETERIA SUSPENDIDA SRL","SUSPENDIDO")));
  const page=await mount();
  try{
    await page.type("131000022");
    const block=page.block()!;
    expect(block.dataset.legalNameStatus).toBe("inactive");
    expect(block.textContent).toContain("No activo");expect(block.textContent).toContain("Según la DGII: SUSPENDIDO");
    expect(document.querySelector('[data-testid="legal-name-confirm"]')).not.toBeNull();
    await page.save();
    expect(writes(calls)).toEqual(["PATCH /business/fiscal-profile","PUT /business/fiscal-profile/legal-name"]);
    expect(page.block()?.dataset.legalNameStatus).toBe("verified");
  }finally{await page.close();}
});

test("a failed lookup shows Ref. and Reintentar, the number still saves, and Reintentar checks again",async()=>{
  let fail=true;
  const calls=server(empty,value=>fail?failure():Response.json(answer(value,"verificado")));
  const page=await mount();
  try{
    await page.type("131000014");
    const block=page.block()!;
    expect(block.dataset.legalNameStatus).toBe("failed");
    expect(block.querySelector('[role="alert"]')?.textContent).toContain("ref-legal-0001".slice(0,4));
    await page.save();
    expect(writes(calls)).toEqual(["PATCH /business/fiscal-profile"]);
    fail=false;
    await act(async()=>page.button("Reintentar").click());await flush();
    expect(page.block()?.dataset.legalNameStatus).toBe("pending");
  }finally{await page.close();}
});

test("a failed confirmation keeps the saved number, shows Ref., and its retry replays only the confirmation",async()=>{
  let failPut=true;
  const calls=server(empty,value=>Response.json(answer(value,"verificado")),{put:call=>failPut?failure(503):Response.json({...empty,tax_id:{type:"rnc",value:"131000014"},legal_name:{value:(call.body as {legal_name:string}).legal_name,confirmed_at:"2026-11-09T12:00:00Z"}})});
  const page=await mount();
  try{
    await page.type("131000014");
    await page.save();
    const alert=document.querySelector('[data-testid="business-fiscal-profile"] [role="alert"]');
    expect(alert?.textContent).toContain("No se pudo leer o guardar el RNC.");
    expect(alert?.textContent).toContain("Ref.");
    expect(page.block()?.dataset.legalNameStatus).toBe("pending");
    failPut=false;
    await page.save();
    expect(writes(calls)).toEqual(["PATCH /business/fiscal-profile","PUT /business/fiscal-profile/legal-name","PUT /business/fiscal-profile/legal-name"]);
    const keys=calls.filter(call=>call.method==="PUT").map(call=>call.key);
    expect(keys[0]).toBeTruthy();expect(keys[1]).toBe(keys[0]);
    expect(page.block()?.dataset.legalNameStatus).toBe("verified");
  }finally{await page.close();}
});

test("a long legal name wraps as plain text and the lookup shows a skeleton with no tag",async()=>{
  let release:(value:Response)=>void=()=>{};
  server(empty,()=>new Promise<Response>(resolve=>{release=resolve;}) as unknown as Response);
  const page=await mount();
  try{
    await page.type("131000014");
    expect(page.block()?.dataset.legalNameStatus).toBe("checking");
    expect(page.block()?.getAttribute("aria-busy")).toBe("true");
    expect(page.block()?.textContent).not.toContain("Por confirmar");
    await act(async()=>release(Response.json(answer("131000014","verificado"))));await flush();
    const value=page.block()?.querySelector<HTMLElement>('[data-testid="legal-name-value"]');
    expect(value?.tagName).toBe("P");expect(value?.className).toContain("[overflow-wrap:anywhere]");
    expect(value?.textContent).toBe(LONG_NAME);
  }finally{await page.close();}
});

test("the English twins render and the copy never says mi, tu or my or your business, nor uses a long dash",async()=>{
  for(const catalog of [spanish,english]){
    const copy=JSON.stringify((catalog as unknown as {business:{dgii:{legal_name:Record<string,string>}}}).business.dgii.legal_name);
    expect(copy).not.toMatch(/\b(mi|tu|my|your) (negocio|business)\b/i);
    expect(copy.includes("—")).toBe(false);
  }
  server(empty,value=>Response.json(answer(value,"verificado")));
  const page=await mount("en");
  try{
    await page.type("131000014");
    expect(page.block()?.textContent).toContain("To confirm");
    expect(document.querySelector('[data-testid="legal-name-confirm"]')?.textContent).toBe("When you save, you confirm that this RNC belongs to La Palma.");
  }finally{await page.close();}
});

test("someone who cannot manage the Business sees no Razón social block and never asks the registry",async()=>{
  const calls=server({...empty,tax_id:{type:"rnc",value:"131000014"},can_edit:false},value=>Response.json(answer(value,"verificado")));
  const page=await mount();
  try{
    expect(document.querySelector('[data-testid="business-fiscal-profile"]')?.textContent).toContain("131000014");
    expect(page.block()).toBeNull();
    expect(calls.some(call=>call.path==="/business/fiscal-profile/registry")).toBe(false);
  }finally{await page.close();}
});
