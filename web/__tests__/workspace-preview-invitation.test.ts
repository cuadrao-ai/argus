import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { runInNewContext } from "node:vm";
import { test } from "bun:test";

const sketch = readFileSync(resolve(import.meta.dir, "../../temp/home-setup/index.html"), "utf8");
const source = [
  sketch.slice(sketch.indexOf("const guideSteps="), sketch.indexOf("function show(")),
  sketch.slice(sketch.indexOf("function render(){"), sketch.indexOf("function renderPreviewTools(")),
  sketch.slice(sketch.indexOf("function inviteView(){"), sketch.indexOf("function bindInvite(")),
].join("\n");

function renderInvitation(language: string, status: string, permission?: string) {
  const locale = JSON.parse(readFileSync(resolve(import.meta.dir, `../public/locales/${language}/common.json`), "utf8")).workspace_setup_preview;
  const nodes = new Map<string, { textContent: string; innerHTML: string; style: Record<string, string>; setAttribute(): void; querySelector(): unknown }>();
  const node = (id: string) => {
    if (!nodes.has(id)) nodes.set(id, { textContent: "", innerHTML: "", style: {}, setAttribute() {}, querySelector() { return node(`${id}-child`); } });
    return nodes.get(id)!;
  };
  const state = { workspace: { name: "Example business" }, view: ["pending", "granted"].includes(status) ? "invite" : "actions", invitation: { email: "collaborator@example.test", status, permission } };
  const context = {
    state, $: node, document: { documentElement: { lang: "" } }, previewLanguage: language,
    inviteSurface: false, invoiceSurface: false, whatsappSurface: false, reviewOnly: false, registryTimer: undefined, registryVersion: 0,
    clearTimeout() {}, invoiceState: () => ({ status: "not-started" }), renderPreviewTools() {}, bindForms() {}, enhancePickers() {},
    esc: (value: string) => value, destination: () => "", back: () => "",
    tr: (key: string, values: Record<string, unknown> = {}) => Object.entries(values).reduce((copy, [name, value]) => copy.replaceAll(`{${name}}`, String(value)), locale[key] ?? key),
  };
  runInNewContext(`${source}\nrender();`, context);
  return { nodes, state, html: node("guidecontent").innerHTML };
}

for (const [language, pending, noAccess] of [
  ["en", "Pending acceptance", "They do not have access yet"],
  ["es-419", "Pendiente de aceptación", "Todavía no tiene acceso"],
]) {
  test(`${language}: a created invitation completes the guide while acceptance and access stay pending`, () => {
    const { nodes, state, html } = renderInvitation(language, "pending");
    assert.equal(nodes.get("progresscount")!.textContent, "2 / 4");
    assert.equal(nodes.get("progressfill")!.style.strokeDashoffset, "50");
    assert.match(html, /<li class="setup-item is-open is-done [^"]*">/);
    const invitationHeading = html.slice(html.indexOf('aria-controls="panel-invite"'), html.indexOf('<div id="panel-invite"'));
    assert.ok(invitationHeading.includes(pending));
    assert.ok(html.includes(noAccess));
    assert.doesNotMatch(html, /invite-status is-granted/);
    assert.equal(state.invitation!.status, "pending");
  });

  for (const status of ["draft", "sending", "error", "deferred"]) {
    test(`${language}: ${status} does not complete the invitation step`, () => {
      const { nodes } = renderInvitation(language, status);
      assert.equal(nodes.get("progresscount")!.textContent, "1 / 4");
      assert.equal(nodes.get("progressfill")!.style.strokeDashoffset, "75");
    });
  }

  test(`${language}: granted access keeps the invitation step complete`, () => {
    const { nodes, html, state } = renderInvitation(language, "granted");
    assert.equal(nodes.get("progresscount")!.textContent, "2 / 4");
    assert.match(html, /invite-status is-granted/);
    assert.equal(state.invitation!.status, "granted");
  });
}


test("a menu draft preserves guide progress and publishes only a created invitation", () => {
  const guideKey = "guide-business-a";
  const key = guideKey + "-invite-draft";
  const guide = { invitation: { email: "first@example.test", status: "pending" }, billing: { status: "in-progress" }, view: "billing" };
  const stored = new Map<string, string>([[guideKey, JSON.stringify(guide)]]);
  const state = { invitation: { email: "second@example.test", status: "draft" }, view: "invite" };
  const context = { state, key, guideKey, inviteSurface: true, navigationKey: "navigation",
    sessionStorage: { setItem() {} },
    localStorage: { getItem: (key: string) => stored.get(key), setItem: (key: string, value: string) => stored.set(key, value) },
  };
  const save = sketch.slice(sketch.indexOf("const saved="), sketch.indexOf("const button="));
  for (const status of ["draft", "sending", "error"]) {
    state.invitation!.status = status;
    runInNewContext(save + "saved();", context);
    assert.deepEqual(JSON.parse(stored.get(guideKey)!), guide);
    assert.equal(JSON.parse(stored.get(key)!).invitation.status, status);
  }
  state.invitation!.status = "pending";
  runInNewContext(save + "saved();", context);
  assert.deepEqual(JSON.parse(stored.get(guideKey)!), { ...guide, invitation: state.invitation });
});


for (const role of ["owner", "admin", "editor", "viewer"]) {
test(`${role} access survives email edits and remains pending after invite creation`, async () => {
  const state = { invitation: { email: "", permission: "editor", status: "draft" } };
  const email = { value: "assistant@example.test" };
  const permission = { value: role, onchange: () => {} };
  const submit = { textContent: "" };
  const form = { querySelector: () => submit, onsubmit: async (event: { preventDefault(): void }) => { void event; } };
  let editEmail = (value: string) => { void value; };
  const nodes: Record<string, unknown> = { inviteform: form, inviteemail: email, invitepermission: permission, "invite-request-error": { textContent: "" } };
  const context = { state, $: (id: string) => nodes[id], bindField: (_id: string, change: typeof editEmail) => { editEmail = change; },
    saved() {}, render() {}, tr: (key: string) => key, validateForm: () => true, normalizeEmail: (value: string) => value.trim(),
    setTimeout: (done: () => void) => done(), URLSearchParams, location: { search: "" }, inviteSurface: true,
    document: { querySelector: () => null },
  };
  const binding = sketch.slice(sketch.indexOf("function bindInvite(){"), sketch.indexOf("function bindForms("));
  runInNewContext(binding + "bindInvite();", context);
  permission.onchange();
  editEmail(email.value);
  assert.equal(state.invitation!.permission, role);
  await form.onsubmit({ preventDefault() {} });
  assert.deepEqual(state.invitation, { email: email.value, permission: role, status: "pending" });
});

}

for (const [language, owner, noAccess] of [["en", "Owner", "They do not have access yet"], ["es-419", "Dueño", "Todavía no tiene acceso"]]) {
  test(`${language}: pending owner invitation retains its role without granting access`, () => {
    const { html, state } = renderInvitation(language, "pending", "owner");
    assert.ok(html.includes(`<strong>${owner}</strong>`));
    assert.ok(html.includes(noAccess));
    assert.doesNotMatch(html, /invite-status is-granted/);
    assert.equal(state.invitation!.permission, "owner");
    assert.equal(state.invitation!.status, "pending");
  });
}


type BatchRecipient = {id: string; email: string; permission: string; status: string; attempts: number; error?: string; touched?: boolean};
type Batch = {draft?: {email: string; permission: string}; recipients: BatchRecipient[]; history: {email: string; permission: string; status: string}[]; phase: string; nextId: number};
type Invitation = {email: string; permission: string; status: string};
const batchSource = sketch.slice(sketch.indexOf("function blankBatchRecipient("), sketch.indexOf("function inviteView(){"));
function batchHarness(language = "en", fixture = "", known?: {email: string; status: string}, legacy?: Batch, member?: {email: string; permission: string}) {
  const locale = JSON.parse(readFileSync(resolve(import.meta.dir, `../public/locales/${language}/common.json`), "utf8")).workspace_setup_preview;
  const state: {invitation?: Invitation; invitationBatch?: Batch} = legacy ? {invitationBatch: legacy} : {};
  const callbacks: (() => void)[] = [];
  const context = {
    state, currentInvitationMember: member ?? null, guideKey: "guide", localStorage: { getItem: () => JSON.stringify({invitation: known}) },
    normalizeEmail: (value: string) => value.trim().toLowerCase(),
    fieldRules: { inviteemail: { check: (value: string) => !value ? "required" : /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? "" : "invalid" } },
    tr: (key: string, values: Record<string, unknown> = {}) => Object.entries(values).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), locale[key] ?? key),
    esc: (value: unknown) => String(value ?? ""), saved() {}, render() {}, $: () => null,
    document: { querySelector: () => null }, button: () => "<button>Cancel</button>",
    setTimeout: (done: () => void) => { callbacks.push(done); }, URLSearchParams, location: { search: `?inviteResult=${fixture}` },
  };
  const api = runInNewContext(batchSource + "({get:invitationBatch, add:addBatchRecipient, reset:resetInvitationBatch, send:sendInvitationBatch, html:batchInviteView, validation:batchRowValidation, people:knownInvitationPeople})", context) as {get(): Batch; add(): string; reset(): void; send(): Promise<void>; html(): string; validation(row: BatchRecipient): {tone: string; message: string}; people(): {access: Invitation[];pending: Invitation[]}};
  const add = (email: string, permission = "editor") => {
    let row = api.get().recipients.find(row => !row.email && row.status === "draft");
    if (!row) { const id = api.add(); row = api.get().recipients.find(row => row.id === id)!; }
    row.email = email; row.permission = permission; return row;
  };
  const finish = async () => { callbacks.splice(0).forEach(done => done()); await Promise.resolve(); };
  return { api, state, add, finish, locale };
}

for (const language of ["en", "es-419"]) {
  test(`${language}: a single owner invite can send directly and stays pending`, async () => {
    const { api, state, add, finish, locale } = batchHarness(language);
    assert.equal(api.get().recipients.length, 1);
    add(" OWNER@example.test ", "owner");
    const sending = api.send();
    assert.equal(api.get().phase,"sending");
    await finish();await sending;
    assert.equal(api.get().phase,"success");
    assert.equal(state.invitation!.email,"owner@example.test");
    assert.equal(state.invitation!.permission,"owner");
    assert.equal(state.invitation!.status,"pending");
    assert.ok(api.html().includes(locale.batch_success_one));
    assert.ok(api.html().includes(locale.batch_no_access));
  });

  test(`${language}: partial retry sends only failed recipients and another batch retains sent history`, async () => {
    const {api,add,finish,state}=batchHarness(language,"partial");
    add("owner@example.test","owner");add("assistant@example.test","editor");add("reader@example.test","viewer");
    const first=api.send();await finish();await first;
    assert.deepEqual(Array.from(api.get().recipients,(row:BatchRecipient)=>row.status),["sent","error","sent"]);
    assert.equal(api.get().phase,"partial");
    assert.equal(state.invitation!.status,"pending");
    api.get().recipients[1].email="corrected@example.test";
    api.get().recipients[1].permission="admin";
    const retry=api.send();await finish();await retry;
    assert.deepEqual(Array.from(api.get().recipients,(row:BatchRecipient)=>row.attempts),[1,2,1]);
    assert.equal(api.get().history.length,3);
    assert.equal(api.get().phase,"success");
    api.reset();
    assert.equal(api.get().recipients.length,1);
    assert.equal(api.get().recipients[0].email,"");
    assert.equal(api.get().recipients[0].permission,"editor");
    assert.equal(api.get().history.length,3);
    assert.equal(state.invitation!.status,"pending");
    const duplicate=add("OWNER@example.test");await api.send();
    assert.ok(duplicate.error);
    duplicate.email="next@example.test";
    const next=api.send();await finish();await next;
    assert.equal(api.get().phase,"success");
    assert.equal(api.get().history.length,4);
  });

  test(`${language}: invalid, duplicate and known-member rows block sending`, async () => {
    const {api,add}=batchHarness(language,"",{email:"member@example.test",status:"granted"});
    const invalid=add("not-an-email");
    const member=add("member@example.test");
    const first=add("person@example.test");
    const duplicate=add(" PERSON@EXAMPLE.TEST ");
    await api.send();
    for (const row of [invalid,member,first,duplicate]) { assert.ok(row.error);assert.equal(row.attempts,0); }
    assert.equal(api.get().phase,"draft");
  });

  test(`${language}: blank extra rows are ignored and an entirely empty list gets a required error`, async () => {
    const {api,add,finish}=batchHarness(language);
    api.add();await api.send();
    assert.ok(api.get().recipients[0].error);
    assert.equal(api.get().recipients[0].attempts,0);
    add("person@example.test");api.add();
    const sending=api.send();await finish();await sending;
    assert.equal(api.get().recipients.length,1);
    assert.equal(api.get().history.length,1);
  });
}

test("existing composer drafts migrate once without losing queued people or successful history", () => {
  const legacy: Batch = {
    draft: {email:"review@example.test", permission:"admin"},
    recipients: [{id:"1", email:"colaborador@example.test", permission:"editor", status:"draft", attempts:0}],
    history: [{email:"prior@example.test", permission:"viewer", status:"pending"}], nextId:2, phase:"draft",
  };
  const {api}=batchHarness("en","",undefined,legacy);
  assert.deepEqual(Array.from(api.get().recipients,row=>[row.email,row.permission]),[
    ["colaborador@example.test","editor"],["review@example.test","admin"],
  ]);
  assert.equal(api.get().recipients.length,2);
  assert.equal(api.get().draft,undefined);
  assert.equal(api.get().history.length,1);
  assert.equal(api.get().nextId,3);
});

test("concurrent submit does not create a second request", async () => {
  const {api,add,finish}=batchHarness();add("one@example.test");
  const first=api.send();await api.send();
  assert.equal(api.get().recipients[0].attempts,1);
  await finish();await first;
  assert.equal(api.get().history.length,1);
});


for (const language of ["en", "es-419"]) {
  test(`${language}: email feedback stays neutral until checked and distinguishes format validity`, () => {
    const {api,add,locale}=batchHarness(language);
    const row=api.get().recipients[0];
    assert.equal(api.validation(row).tone,"neutral");
    add("broken");
    assert.equal(api.validation(row).tone,"neutral");
    row.touched=true;
    assert.equal(api.validation(row).tone,"error");
    row.email="valid@example.test";
    assert.equal(api.validation(row).tone,"valid");
    assert.equal(api.validation(row).message,locale.batch_email_format_valid);
    assert.ok(api.html().includes('data-validation="valid"'));
    row.touched=false;row.email="edited@example.test";
    assert.equal(api.validation(row).tone,"neutral");
  });

  test(`${language}: duplicate email feedback recovers when another row changes or is removed`, () => {
    const {api,add}=batchHarness(language);
    const first=add("person@example.test");first.touched=true;
    assert.equal(api.validation(first).tone,"valid");
    const second=add("PERSON@example.test");second.touched=true;
    assert.equal(api.validation(first).tone,"error");
    assert.equal(api.validation(second).tone,"error");
    second.email="another@example.test";
    assert.equal(api.validation(first).tone,"valid");
    assert.equal(api.validation(second).tone,"valid");
    second.email=first.email;
    api.get().recipients=api.get().recipients.filter(row=>row!==second);
    assert.equal(api.validation(first).tone,"valid");
  });

  test(`${language}: a send failure never earns a valid-format check`, async () => {
    const {api,add,finish,locale}=batchHarness(language,"error");
    const row=add("person@example.test");row.touched=true;
    const sending=api.send();await finish();await sending;
    assert.equal(api.validation(row).tone,"error");
    assert.equal(api.validation(row).message,locale.batch_send_error);
    assert.ok(api.html().includes('data-validation="error"'));
    assert.ok(!api.html().includes('data-validation="valid"'));
  });
}


for (const language of ["en", "es-419"]) {
  test(`${language}: known access is deduplicated separately from pending, with session access winning`, () => {
    const {api}=batchHarness(language,"",undefined,undefined,{email:"OWNER@example.test",permission:"owner"});
    api.get().history.push(
      {email:"owner@example.test",permission:"editor",status:"granted"},
      {email:"accepted@example.test",permission:"admin",status:"granted"},
      {email:"ACCEPTED@example.test",permission:"viewer",status:"pending"},
      {email:"pending@example.test",permission:"viewer",status:"pending"},
      {email:"PENDING@example.test",permission:"viewer",status:"pending"},
    );
    const known=api.people();
    assert.equal(known.access.length,2);
    assert.equal(known.pending.length,1);
    assert.equal(known.access.find(person=>person.email==="owner@example.test")!.permission,"owner");
    assert.equal(known.access.find(person=>person.email==="accepted@example.test")!.permission,"admin");

  });

  test(`${language}: the signed-in member cannot receive a duplicate self-invite`, async () => {
    const {api,add,locale}=batchHarness(language,"",undefined,undefined,{email:"owner@example.test",permission:"owner"});
    const row=add(" OWNER@example.test ");await api.send();
    assert.equal(row.error,locale.batch_member);
    assert.equal(row.attempts,0);
    assert.equal(api.people().pending.length,0);
  });
}

test("missing identity does not invent a member or owner role", () => {
  const {api}=batchHarness();
  assert.equal(api.people().access.length,0);
  assert.equal(api.people().pending.length,0);
});

test("session identity is accepted only for the selected business and is not persisted in guide state", () => {
  const state={workspace:{name:"Business"},documentReceived:false,collapsed:false,expansionChosen:true};
  const context={state,businessScope:"business-a",currentInvitationMember:null,normalizeInvoiceProgress:()=>false,saved(){},render(){}};
  const source=sketch.slice(sketch.indexOf("function applyBusinessContext("),sketch.indexOf("function render(){"));
  const run=(businessId:string,email?:string)=>runInNewContext(source+`;applyBusinessContext(${JSON.stringify({businessId,name:"Business",country:"DO",shared:false,currentMember:email?{email,permission:"owner"}:null})});currentInvitationMember;`,context);
  assert.equal(run("business-b","wrong@example.test"),null);
  assert.equal(run("business-a","owner@example.test").email,"owner@example.test");
  assert.equal(run("business-a"),null);
  assert.ok(!("currentInvitationMember" in state));
});

test("cancelled pending can be invited again without reviving stale guide state", async () => {
  const {api,state,add,finish}=batchHarness();
  state.invitation={email:"cancelled@example.test",permission:"owner",status:"pending"};
  api.get().history.push({...state.invitation,status:"cancelled"});
  assert.equal(api.people().pending.length,0);
  const row=add("cancelled@example.test","editor");
  const sending=api.send();await finish();await sending;
  assert.equal(row.status,"sent");
  assert.equal(api.people().pending.length,1);
  assert.equal(api.people().pending[0].permission,"editor");
  assert.equal(api.people().access.length,0);
});
