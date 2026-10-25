import {expect,test} from "bun:test";
import {aliasError,readReceptionPreview,saveReceptionAlias,suggestedReceptionAliases,saveReceptionReading} from "../app/design-workspace/businessReceptionPreviewState";
import {invitationStorageKeys} from "../app/design-workspace/businessAccessPreviewState";
function memory() {
  const values=new Map<string,string>();
  return {get length(){return values.size;},getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value);},key:(index:number)=>[...values.keys()][index]??null};
}
test("one alias customization preserves guide facts and cannot be repeated",()=>{
  const storage=memory(),key=invitationStorageKeys("palma").guide;
  storage.setItem(key,JSON.stringify({workspace:{name:"La Palma"},businessProvidedDetails:{phone:"555"},whatsapp:{linked:true,last4:"0123"}}));
  expect(saveReceptionAlias(storage,"palma","la-palma","recibos-123@recibos.example")).toBe("la-palma@recibos.example");
  expect(readReceptionPreview(storage,"palma")).toEqual({address:"la-palma@recibos.example",linked:true,last4:"0123",reading:false});
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

test("business-name suggestions are deterministic, distinct and valid even at name boundaries",()=>{
  const storage=memory();
  expect(suggestedReceptionAliases("La Palma","nombre-del-negocio")).toEqual(["la-palma","lapalma","la-palma-recibos"]);
  for(const name of ["Café Ñúñez","A B","1 2","A","12","---","","公司","x".repeat(80),"La Palma ".repeat(20)]) {
    const aliases=suggestedReceptionAliases(name,"nombre-del-negocio");
    expect(aliases).toHaveLength(3);expect(new Set(aliases).size).toBe(3);
    for(const alias of aliases)expect(aliasError(storage,"test",alias,"recibos.example")).toBeNull();
  }
  expect(suggestedReceptionAliases("Café Ñúñez","nombre-del-negocio")[0]).toBe("cafe-nunez");
});

test("mock receipt reading persists per business without changing guide facts",()=>{
  const storage=memory();
  saveReceptionAlias(storage,"palma","la-palma","default@recibos.example");
  expect(readReceptionPreview(storage,"palma").reading).toBe(false);
  saveReceptionReading(storage,"palma",true);
  expect(readReceptionPreview(storage,"palma").reading).toBe(true);
  expect(readReceptionPreview(storage,"palma").address).toBe("la-palma@recibos.example");
  expect(readReceptionPreview(storage,"other").reading).toBe(false);
  saveReceptionReading(storage,"palma",false);
  expect(readReceptionPreview(storage,"palma").reading).toBe(false);
});
