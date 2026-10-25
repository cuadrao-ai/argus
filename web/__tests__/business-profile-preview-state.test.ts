import {expect,test} from "bun:test";
import {readBusinessProfilePreview,saveBusinessProfilePreview} from "../app/design-workspace/businessProfilePreviewState";
import {invitationStorageKeys} from "../app/design-workspace/businessAccessPreviewState";
function store(businessId:string,value:unknown){const values=new Map([[invitationStorageKeys(businessId).guide,JSON.stringify(value)]]);return {getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value);}};}
test("profile facts stay business scoped and a missing tax ID stays unknown",()=>{
 const storage=store("one",{workspace:{name:"Saved name",country:"DO"},businessDetails:{enteredRnc:"131245678"}});
 const current=readBusinessProfilePreview(storage,"one","Display name");
 expect(current.name).toBe("Display name");expect(current.country).toBe("DO");expect(current.taxId?.value).toBe("131245678");
 const other=readBusinessProfilePreview(storage,"two","Second business");
 expect(other.country).toBeNull();expect(other.taxId).toBeNull();expect(other.legalName).toBeNull();expect(other.invoice.action).toBe("configure");
});
test("legal name needs a confirmed match for the current RNC",()=>{
 const details={enteredRnc:"131-245678",legalName:"Typed name"};
 const lookup={status:"match",queriedRnc:"131245678",record:{rnc:"131245678",legalName:"Registry name"},confirmedAt:"2026-10-24"};
 expect(readBusinessProfilePreview(store("one",{businessDetails:details,registryResult:lookup}),"one","Display").legalName).toBe("Registry name");
 expect(readBusinessProfilePreview(store("one",{businessDetails:details,registryResult:lookup,taxnumber:"999999999"}),"one","Display").legalName).toBeNull();
 expect(readBusinessProfilePreview(store("one",{businessDetails:details,registryResult:lookup,taxnumber:""}),"one","Display").legalName).toBeNull();
 for(const result of [{...lookup,confirmedAt:null},{...lookup,status:"review"},{...lookup,queriedRnc:"999999999"},{...lookup,record:{rnc:"999999999",legalName:"Wrong business"}}]){
  expect(readBusinessProfilePreview(store("one",{businessDetails:details,registryResult:result}),"one","Display").legalName).toBeNull();
 }
});
test("invoicing action derives from saved status and never from an entered tax ID",()=>{
 for(const [status,path,action] of [["not-started",null,"configure"],["in-progress","new","continue"],["needs-information","existing","continue"],["awaiting-verification","new","view"],["active","existing","view"]] as const){
  const state=store("one",{activation:{status,path},businessDetails:{enteredRnc:"131245678",legalName:"Typed name"}});
  expect(readBusinessProfilePreview(state,"one","Business").invoice.action).toBe(action);
 }
 expect(readBusinessProfilePreview(store("one",{activation:{status:"awaiting-verification",path:"new"}}),"one","Business").invoice.status).toBe("needs-information");
});
test("saving name and tax ID preserves guide history and invalidates a stale registry match",()=>{
 const storage=store("one",{workspace:{name:"Original",country:"DO"},invitation:{status:"pending",email:"pending@example.test"},businessDetails:{enteredRnc:"131245678",legalName:"Existing legal name",registryRecord:{rnc:"131245678"},confirmedAt:"2026-10-24"},registryResult:{status:"match",confirmedAt:"2026-10-24",queriedRnc:"131245678",record:{rnc:"131245678",legalName:"Registry name"}}});
 saveBusinessProfilePreview(storage,"one",{name:"Updated",previous_name:"Original",tax_id:{type:"rnc",value:"999-999999"},previous_tax_id:{type:"rnc",value:"131245678"}});
 const updated=readBusinessProfilePreview(storage,"one","Updated");
 expect(updated.name).toBe("Updated");expect(updated.country).toBe("DO");expect(updated.taxId?.value).toBe("999999999");expect(updated.legalName).toBeNull();
 const raw=JSON.parse(storage.getItem(invitationStorageKeys("one").guide)!);
 expect(raw.invitation.email).toBe("pending@example.test");expect(raw.businessDetails.legalName).toBe("");expect(raw.legalname).toBe("");expect(raw.registryResult).toBeNull();
 saveBusinessProfilePreview(storage,"one",{name:"Updated",previous_name:"Updated",tax_id:{type:"cedula",value:"001-12345678"},previous_tax_id:updated.taxId});
 expect(readBusinessProfilePreview(storage,"one","Updated").taxId).toEqual({type:"cedula",value:"00112345678"});
});
