import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { runInNewContext } from "node:vm";
import { test } from "bun:test";

const sketch = readFileSync(resolve(import.meta.dir, "../../temp/home-setup/index.html"), "utf8");
const invoice = readFileSync(resolve(import.meta.dir, "../../temp/home-setup/invoicing.js"), "utf8");
const contextFunction = sketch.slice(sketch.indexOf("function applyBusinessContext("), sketch.indexOf("function render(){"));
const invoiceFunction = invoice.slice(0, invoice.indexOf("function invoiceStatus("));

test("selected Business context preserves drafts and expansion while receipt outcomes update", () => {
  const state = { workspace: { name: "Old", country: "DO" }, workspaceNameDraft: "Unfinished edit", expansionChosen: false, collapsed: false, view: "create" };
  const env = { state, businessScope: "a", saved() {}, render() {} };
  runInNewContext(`${invoiceFunction}\n${contextFunction}\napplyBusinessContext({businessId:'other',name:'Wrong',country:'US',documentReceived:true});`, env);
  assert.equal(state.workspace.name, "Old");
  runInNewContext(`${invoiceFunction}\n${contextFunction}\napplyBusinessContext({businessId:'a',name:'Current',country:null,documentReceived:true});`, env);
  assert.equal(state.workspace.name, "Current");
  assert.equal(state.workspace.country, "DO");
  assert.equal(state.workspaceNameDraft, "Unfinished edit");
  assert.equal(state.collapsed, true);
  assert.equal((state as typeof state & { documentReceived: boolean }).documentReceived, true);
  state.expansionChosen = true;
  state.collapsed = false;
  state.view = "workspace-rename";
  runInNewContext(`${invoiceFunction}\n${contextFunction}\napplyBusinessContext({businessId:'a',name:'Current',country:'DO',documentReceived:false});`, env);
  assert.equal(state.collapsed, false);
  assert.equal(state.view, "workspace-rename");
  assert.equal((state as typeof state & { documentReceived: boolean }).documentReceived, true, "processing or an empty page cannot undo receipt history");
});

test("a restored incomplete review state becomes needs information without losing its draft", () => {
  const state = { activation: { path: "new", status: "awaiting-verification", step: "overview" }, businessDetails: { enteredRnc: "", legalName: "" }, legalname: "Draft name" };
  let saves = 0;
  runInNewContext(`${invoiceFunction}\ninvoiceState();`, { state, saved() { saves++; } });
  assert.equal(state.activation.status, "needs-information");
  assert.equal(state.activation.step, "details");
  assert.equal(state.legalname, "Draft name");
  assert.equal(saves, 1);
  state.businessDetails = { enteredRnc: "123456789", legalName: "Saved business" };
  state.activation.status = "awaiting-verification";
  runInNewContext(`${invoiceFunction}\ninvoiceState();`, { state, saved() { saves++; } });
  assert.equal(state.activation.status, "awaiting-verification");
  assert.equal(saves, 1);
});
