import {expect,test} from "bun:test";
import {aliasError,readReceptionPreview,saveReceptionAlias} from "../app/design-workspace/businessReceptionPreviewState";
import {invitationStorageKeys} from "../app/design-workspace/businessAccessPreviewState";
function memory() {
  const values=new Map<string,string>();
  return {get length(){return values.size;},getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value);},key:(index:number)=>[...values.keys()][index]??null};
}
test("one alias customization preserves guide facts and cannot be repeated",()=>{
  const storage=memory(),key=invitationStorageKeys("palma").guide;
  storage.setItem(key,JSON.stringify({workspace:{name:"La Palma"},businessProvidedDetails:{phone:"555"},whatsapp:{linked:true,last4:"0123"}}));
  expect(saveReceptionAlias(storage,"palma","la-palma","recibos-123@recibos.example")).toBe("la-palma@recibos.example");
  expect(readReceptionPreview(storage,"palma")).toEqual({address:"la-palma@recibos.example",linked:true,last4:"0123"});
  expect(JSON.parse(storage.getItem(key)!).businessProvidedDetails.phone).toBe("555");
  expect(()=>saveReceptionAlias(storage,"palma","otro","recibos-123@recibos.example")).toThrow("locked");
  expect(readReceptionPreview(storage,"other").address).toBeNull();
});
test("format and local collisions reject without writing another business",()=>{
  const storage=memory();
  for(const alias of ["a","-abc","abc-","A BC","a".repeat(33)])expect(aliasError(storage,"a",alias,"recibos.example")).toBe("format");
  expect(aliasError(storage,"a","","recibos.example")).toBe("required");
  saveReceptionAlias(storage,"a","palma","default@recibos.example");
  expect(aliasError(storage,"b","palma","recibos.example")).toBe("taken");
  expect(()=>saveReceptionAlias(storage,"b","palma","other@recibos.example")).toThrow("taken");
  expect(readReceptionPreview(storage,"b").address).toBeNull();
});
