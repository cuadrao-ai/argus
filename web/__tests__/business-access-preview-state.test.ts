import { expect, test } from "bun:test";
import { accessActionGuard, changeAccessPreview, invitationStorageKeys, readAccessPreview, seedAccessPreview } from "../app/design-workspace/businessAccessPreviewState";
const actor = {email:"owner@example.test",permission:"owner" as const};
function fixture() {
  const data = new Map<string,string>();
  const store = {getItem:(key:string) => data.get(key) ?? null,setItem:(key:string,value:string) => {data.set(key,value);}};
  const keys = invitationStorageKeys("fixture-space");
  const draft = {invitationBatch:{recipients:[{id:"one",email:"review@example.test",permission:"admin",status:"draft"}],phase:"draft",nextId:2,history:[{email:"pending@example.test",permission:"owner",status:"pending"}]}};
  store.setItem(keys.draft,JSON.stringify(draft));
  store.setItem(keys.guide,JSON.stringify({invitation:{email:"pending@example.test",permission:"owner",status:"pending"},view:"actions"}));
  return {store,keys,draft};
}
test("fixture seed is business scoped, idempotent and preserves recipient drafts", () => {
  const {store,keys,draft}=fixture();
  expect(seedAccessPreview(store,"fixture-space")).toBe(true);
  expect(seedAccessPreview(store,"fixture-space")).toBe(false);
  const saved=JSON.parse(store.getItem(keys.draft)!);
  expect(saved.invitationBatch.recipients).toEqual(draft.invitationBatch.recipients);
  expect(saved.invitationBatch.nextId).toBe(2);
  const view=readAccessPreview(store,"fixture-space",actor);
  expect(view.members[0].current).toBe(true);
  expect(view.members).toHaveLength(4);
  expect(view.pending).toHaveLength(1);
  expect(seedAccessPreview(store,"other")).toBe(false);
  expect(readAccessPreview(store,"other",null)).toEqual({members:[],pending:[]});
});
test("accepted and pending role changes preserve row order and do not grant pending access", () => {
  const {store}=fixture();seedAccessPreview(store,"fixture-space");
  const before=readAccessPreview(store,"fixture-space",actor).members.map(person=>person.email);
  expect(changeAccessPreview(store,"fixture-space",actor,{kind:"role",email:"assistant@example.test",permission:"admin"})).toBeNull();
  expect(changeAccessPreview(store,"fixture-space",actor,{kind:"role",email:"pending@example.test",permission:"editor"})).toBeNull();
  const view=readAccessPreview(store,"fixture-space",actor);
  expect(view.members.map(person=>person.email)).toEqual(before);
  expect(view.members.find(person=>person.email==="assistant@example.test")?.permission).toBe("admin");
  expect(view.pending[0]).toMatchObject({permission:"editor",status:"pending"});
});
test("only owners assign owner; last owner and signed-in user remain protected", () => {
  const {store}=fixture();seedAccessPreview(store,"fixture-space");
  const admin={email:"accountant@example.test",permission:"admin" as const};
  expect(changeAccessPreview(store,"fixture-space",admin,{kind:"role",email:"assistant@example.test",permission:"owner"})).toBe("owner_only");
  expect(changeAccessPreview(store,"fixture-space",actor,{kind:"remove",email:actor.email})).toBe("last_owner");
  expect(changeAccessPreview(store,"fixture-space",actor,{kind:"role",email:actor.email,permission:"editor"})).toBe("last_owner");
  changeAccessPreview(store,"fixture-space",actor,{kind:"role",email:"assistant@example.test",permission:"owner"});
  expect(changeAccessPreview(store,"fixture-space",actor,{kind:"remove",email:actor.email})).toBe("self");
  expect(accessActionGuard(readAccessPreview(store,"fixture-space",null),{email:"external@example.test",permission:"owner"},{kind:"remove",email:"assistant@example.test"})).toBe("last_owner");
});
test("resend stays pending; cancellation masks stale guide without undoing completion", () => {
  const {store,keys,draft}=fixture();const guideBefore=store.getItem(keys.guide);
  expect(changeAccessPreview(store,"fixture-space",actor,{kind:"resend",email:"PENDING@example.test"})).toBeNull();
  expect(readAccessPreview(store,"fixture-space",actor).pending[0]).toMatchObject({status:"pending",resendCount:1});
  expect(changeAccessPreview(store,"fixture-space",actor,{kind:"cancel",email:"pending@example.test"})).toBeNull();
  expect(readAccessPreview(store,"fixture-space",actor).pending).toHaveLength(0);
  expect(store.getItem(keys.guide)).toBe(guideBefore);
  const saved=JSON.parse(store.getItem(keys.draft)!);
  expect(saved.invitationBatch.recipients).toEqual(draft.invitationBatch.recipients);
  expect(saved.invitationBatch.history[0].status).toBe("cancelled");
});
test("revoked fixture access stays removed after reopening and seeding", () => {
  const {store}=fixture();seedAccessPreview(store,"fixture-space");
  expect(changeAccessPreview(store,"fixture-space",actor,{kind:"remove",email:"assistant@example.test"})).toBeNull();
  seedAccessPreview(store,"fixture-space");
  expect(readAccessPreview(store,"fixture-space",actor).members.some(person=>person.email==="assistant@example.test")).toBe(false);
});
test("case-insensitive dedupe gives the session identity precedence over old history", () => {
  const {store,keys}=fixture();
  store.setItem(keys.draft,JSON.stringify({invitationBatch:{history:[{email:"OWNER@example.test",permission:"viewer",status:"granted"},{email:"owner@example.test",permission:"editor",status:"pending"}]}}));
  const view=readAccessPreview(store,"fixture-space",actor);
  expect(view.members).toEqual([{...actor,status:"granted",current:true}]);
  expect(view.pending.some(person=>person.email===actor.email)).toBe(false);
});
