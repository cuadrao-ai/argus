import {expect,test} from "bun:test";
import {readBusinessProfilePreview,saveBusinessProfilePreview,normalizeBusinessProvidedDetails,saveBusinessProvidedDetails} from "../app/design-workspace/businessProfilePreviewState";
import {invitationStorageKeys} from "../app/design-workspace/businessAccessPreviewState";
function store(businessId:string,value:unknown){const values=new Map([[invitationStorageKeys(businessId).guide,JSON.stringify(value)]]);return {getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value);}};}
test("profile facts stay business scoped and a missing tax ID stays unknown",()=>{
 const storage=store("one",{workspace:{name:"Saved name",country:"DO"},businessDetails:{enteredRnc:"131245678"}});
 const current=readBusinessProfilePreview(storage,"one","Display name");
 expect(current.name).toBe("Display name");expect(current.country).toBe("DO");expect(current.taxId?.value).toBe("131245678");
 const other=readBusinessProfilePreview(storage,"two","Second business");
 expect(other.country).toBeNull();expect(other.taxId).toBeNull();expect(other.legalName).toBeNull();expect(other.invoice.action).toBe("configure");
});
test("browser storage never supplies a legal name, even a confirmed registry match",()=>{
 const details={enteredRnc:"131-245678",legalName:"Typed name",lookupStatus:"match",confirmedAt:"2026-10-24",registryRecord:{rnc:"131245678",legalName:"Registry name"}};
 const lookup={status:"match",queriedRnc:"131245678",record:{rnc:"131245678",legalName:"Registry name"},confirmedAt:"2026-10-24"};
 const read=readBusinessProfilePreview(store("one",{businessDetails:details,registryResult:lookup}),"one","Display");
 expect(read.legalName).toBeNull();expect(read.checklist.find(item=>item.key==="legalName")?.complete).toBe(false);
});
test("invoicing action derives from saved status and never from an entered tax ID",()=>{
 for(const [status,path,action] of [["not-started",null,"configure"],["in-progress","new","continue"],["needs-information","existing","continue"],["awaiting-verification","new","view"],["active","existing","view"]] as const){
  const state=store("one",{activation:{status,path},businessDetails:{enteredRnc:"131245678",legalName:"Typed name"}});
  expect(readBusinessProfilePreview(state,"one","Business").invoice.action).toBe(action);
 }
 expect(readBusinessProfilePreview(store("one",{activation:{status:"awaiting-verification",path:"new"}}),"one","Business").invoice.status).toBe("needs-information");
});
test("saving name and tax ID preserves guide history",()=>{
 const storage=store("one",{workspace:{name:"Original",country:"DO"},invitation:{status:"pending",email:"pending@example.test"},businessDetails:{enteredRnc:"131245678",legalName:"Existing legal name",registryRecord:{rnc:"131245678"},confirmedAt:"2026-10-24"},registryResult:{status:"match",confirmedAt:"2026-10-24",queriedRnc:"131245678",record:{rnc:"131245678",legalName:"Registry name"}}});
 saveBusinessProfilePreview(storage,"one",{name:"Updated",previous_name:"Original",tax_id:{type:"rnc",value:"999-999999"},previous_tax_id:{type:"rnc",value:"131245678"}});
 const updated=readBusinessProfilePreview(storage,"one","Updated");
 expect(updated.name).toBe("Updated");expect(updated.country).toBe("DO");expect(updated.taxId?.value).toBe("999999999");expect(updated.legalName).toBeNull();
 const raw=JSON.parse(storage.getItem(invitationStorageKeys("one").guide)!);
 expect(raw.invitation.email).toBe("pending@example.test");expect(raw.businessDetails.enteredRnc).toBe("999999999");
 saveBusinessProfilePreview(storage,"one",{name:"Updated",previous_name:"Updated",tax_id:{type:"cedula",value:"001-12345678"},previous_tax_id:updated.taxId});
 expect(readBusinessProfilePreview(storage,"one","Updated").taxId).toEqual({type:"cedula",value:"00112345678"});
});

test("contact saves stay scoped, normalize optional values, and preserve guide data",()=>{
 const storage=store("one",{workspace:{country:"DO"},activation:{status:"in-progress",path:"existing"},invitation:{email:"assistant@example.test"}});
 const input=normalizeBusinessProvidedDetails({address:"  Calle Sol 10  ",website:"lapalma.do",email:" office@example.test "});
 const saved=saveBusinessProvidedDetails(storage,"one",input);
 expect(saved.address).toBe("Calle Sol 10");expect(saved.website).toBe("lapalma.do");
 expect(readBusinessProfilePreview(storage,"one","La Palma").providedDetails.email).toBe("office@example.test");
 expect(readBusinessProfilePreview(storage,"two","Other").providedDetails.address).toBe("");
 const raw=JSON.parse(storage.getItem(invitationStorageKeys("one").guide)!);
 expect(raw.activation).toEqual({status:"in-progress",path:"existing"});expect(raw.invitation.email).toBe("assistant@example.test");
 expect(raw.registryResult).toBeUndefined();expect(raw.checkedAt).toBeUndefined();
});
test("the local preview has no server and no format rule: it keeps what was typed, and a failed write keeps stored facts",()=>{
 const storage=store("one",{businessProvidedDetails:{email:"saved@example.test"}});
 const typed=normalizeBusinessProvidedDetails({email:"invalid",website:"javascript:alert(1)",phone:"abc 12"});
 expect(saveBusinessProvidedDetails(storage,"one",typed)).toEqual(typed);
 const blocked=store("one",{businessProvidedDetails:{email:"saved@example.test"}});
 expect(()=>saveBusinessProvidedDetails({getItem:blocked.getItem,setItem:()=>{throw new Error("quota");}},"one",normalizeBusinessProvidedDetails({phone:"809 555 0100"}))).toThrow("quota");
 expect(readBusinessProfilePreview(blocked,"one","La Palma").providedDetails.email).toBe("saved@example.test");
});
test("checklist uses saved facts without requiring province or municipality",()=>{
 const storage=store("one",{businessDetails:{enteredRnc:"123"},businessProvidedDetails:{address:"Calle Sol"}});
 const item=(key:string)=>readBusinessProfilePreview(storage,"one","La Palma").checklist.find(item=>item.key===key)?.complete;
 expect(item("address")).toBe(true);expect(item("taxId")).toBe(false);expect(item("legalName")).toBe(false);expect(item("email")).toBe(false);expect(item("website")).toBe(false);
 saveBusinessProvidedDetails(storage,"one",normalizeBusinessProvidedDetails({email:"office@example.test"}));expect(item("email")).toBe(true);expect(item("address")).toBe(false);
 for(const value of ["131245678","00112345678"]){const taxId=value.length===9 ? {businessDetails:{enteredRnc:value}} : {profileTaxId:{type:"cedula",value}};expect(readBusinessProfilePreview(store("one",taxId),"one","Business").checklist.find(item=>item.key==="taxId")?.complete).toBe(true);}
});
