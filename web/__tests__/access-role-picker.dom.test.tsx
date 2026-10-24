import assert from "node:assert/strict";
import {afterAll,beforeAll,test} from "bun:test";
import {GlobalRegistrator} from "@happy-dom/global-registrator";

beforeAll(() => {
  GlobalRegistrator.register({url:"http://localhost/biz"});
  (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
});
afterAll(async () => {await GlobalRegistrator.unregister();});

async function mount(phone=false, framed=false) {
  (window as unknown as {happyDOM:{setWindowSize:(size:{width:number;height:number})=>void}}).happyDOM.setWindowSize({width:phone?390:1280,height:800});
  const {act,useState}=await import("react");
  const i18next=(await import("i18next")).default;
  const {I18nextProvider}=await import("react-i18next");
  const i18n=i18next.createInstance();
  await i18n.init({lng:"en",resources:{en:{translation:{common:{close:"Close",back:"Back"},workspace_setup_preview:{permission_label:"Access"}}}}});
  const {createRoot}=await import("react-dom/client");
  const {createPortal}=await import("react-dom");
  const Picker=(await import("../app/design-workspace/AccessRolePicker")).default;
  const InvitationPicker=(await import("../app/design-workspace/InvitationAccessPicker")).default;
  const host=document.createElement("div");document.body.append(host);
  const frame=framed?document.createElement("iframe"):null;
  if(frame)document.body.append(frame);
  const frameDocument=frame?.contentDocument;
  const field=frameDocument?.createElement("div");
  if(field){field.innerHTML='<select><option value="editor" data-description="Prepares records">Editor</option><option value="viewer" data-description="Reads records">Viewer</option></select><span data-compact="true" data-label="Access"></span>';frameDocument!.body.append(field);}
  const options=[{value:"owner",label:"Owner",description:"Manages ownership"},{value:"editor",label:"Editor",description:"Prepares records"},{value:"viewer",label:"Viewer",description:"Reads records"}];
  let selected="editor";
  function Harness(){const[value,setValue]=useState("editor");return framed?createPortal(<InvitationPicker slot={field!.querySelector("span")!}/>,field!.querySelector("span")!):<><Picker compact variant="quiet" label="Access" options={options} value={value} onChange={value=>{selected=value;setValue(value);}}/><button id="after-picker">After</button></>;}
  const root=createRoot(host);
  await act(async()=>root.render(<I18nextProvider i18n={i18n}><Harness/></I18nextProvider>));
  const trigger=(frameDocument??document).querySelector<HTMLButtonElement>('[role="combobox"]')!;
  const click=(node:HTMLElement)=>act(async()=>node.click());
  const key=(name:string)=>act(async()=>{document.activeElement!.dispatchEvent(new KeyboardEvent("keydown",{key:name,bubbles:true}));});
  const idle=()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve,30));});
  return {trigger,click,key,idle,selected:()=>selected,frame,field,act,close:()=>act(async()=>{root.unmount();host.remove();frame?.remove();})};
}
test("desktop reuses descriptive options, keyboard selection and trigger focus return",async()=>{
  const view=await mount();try{
    await view.click(view.trigger);
    const options=[...document.querySelectorAll<HTMLButtonElement>('[role="option"]')];
    assert.equal(options.length,3);
    assert.equal(options[1].getAttribute("aria-selected"),"true");
    assert.ok(options[1].textContent?.includes("Prepares records"));
    assert.equal(document.activeElement,options[1]);
    await view.key("Home");assert.equal(document.activeElement,options[0]);
    await view.key("End");assert.equal(document.activeElement,options[2]);
    await view.key("ArrowUp");assert.equal(document.activeElement,options[1]);
    await view.click(options[2]);await view.idle();
    assert.equal(view.selected(),"viewer");assert.equal(document.querySelector('[role="listbox"]'),null);
    assert.equal(document.activeElement,view.trigger);
  }finally{await view.close();}
});
test("Escape and outside press dismiss the desktop popup without changing access",async()=>{
  const view=await mount();try{
    await view.click(view.trigger);await view.key("Escape");await view.idle();
    assert.equal(document.querySelector('[role="listbox"]'),null);assert.equal(document.activeElement,view.trigger);
    await view.click(view.trigger);
    await view.act(async()=>document.body.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true})));
    assert.equal(document.querySelector('[role="listbox"]'),null);assert.equal(view.selected(),"editor");
  }finally{await view.close();}
});
test("phone uses the existing tray and selecting returns to the same trigger",async()=>{
  const view=await mount(true);try{
    await view.click(view.trigger);
    assert.ok(document.querySelector('[role="dialog"]'));
    const selected=document.querySelector<HTMLButtonElement>('[role="option"][aria-selected="true"]')!;
    await view.act(async()=>selected.focus());
    await view.key("End");
    assert.ok(document.activeElement?.textContent?.includes("Viewer"));
    const viewer=[...document.querySelectorAll<HTMLButtonElement>('[role="option"]')].find(node=>node.textContent?.includes("Viewer"))!;
    await view.click(viewer);await view.idle();
    assert.equal(view.selected(),"viewer");assert.equal(document.querySelector('[role="listbox"]'),null);
    assert.equal(document.activeElement,view.trigger);
  }finally{await view.close();}
});
test("invitation iframe adapter keeps its native data source and returns focus across documents",async()=>{
  const view=await mount(false,true);try{
    let changed=0;view.field!.querySelector("select")!.addEventListener("change",()=>changed++);
    await view.click(view.trigger);
    const viewer=[...document.querySelectorAll<HTMLButtonElement>('[role="option"]')].find(node=>node.textContent?.includes("Viewer"))!;
    await view.click(viewer);await view.idle();
    assert.equal(view.field!.querySelector("select")!.value,"viewer");assert.equal(changed,1);
    assert.equal(view.frame!.contentDocument!.activeElement,view.trigger);
  }finally{await view.close();}
});

test("Tab leaves the popup for the following control without selecting a role",async()=>{
  const view=await mount();try{
    const after=document.getElementById("after-picker")!;
    for(const node of [view.trigger,after])Object.defineProperty(node,"getClientRects",{value:()=>[new DOMRect(0,0,100,44)]});
    await view.click(view.trigger);await view.key("Tab");
    assert.equal(document.querySelector('[role="listbox"]'),null);
    assert.equal(document.activeElement,after);assert.equal(view.selected(),"editor");
  }finally{await view.close();}
});

test("server rendering does not require document or window",async()=>{
  const {renderToString}=await import("react-dom/server");
  const Picker=(await import("../app/design-workspace/AccessRolePicker")).default;
  const i18next=(await import("i18next")).default;
  const {I18nextProvider}=await import("react-i18next");
  const i18n=i18next.createInstance();
  await i18n.init({lng:"en",resources:{en:{translation:{}}}});
  const savedDocument=Object.getOwnPropertyDescriptor(globalThis,"document");
  const savedWindow=Object.getOwnPropertyDescriptor(globalThis,"window");
  try{
    Reflect.deleteProperty(globalThis,"document");Reflect.deleteProperty(globalThis,"window");
    const html=renderToString(<I18nextProvider i18n={i18n}><Picker compact variant="quiet" label="Access" value="editor" options={[{value:"editor",label:"Editor",description:"Prepares records"}]} onChange={()=>{}}/></I18nextProvider>);
    assert.ok(html.includes('role="combobox"'));assert.ok(html.includes("Editor"));
  }finally{
    if(savedDocument)Object.defineProperty(globalThis,"document",savedDocument);
    if(savedWindow)Object.defineProperty(globalThis,"window",savedWindow);
  }
});
