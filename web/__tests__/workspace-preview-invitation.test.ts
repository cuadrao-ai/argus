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

function renderInvitation(language: string, status: string) {
  const locale = JSON.parse(readFileSync(resolve(import.meta.dir, `../public/locales/${language}/common.json`), "utf8")).workspace_setup_preview;
  const nodes = new Map<string, { textContent: string; innerHTML: string; style: Record<string, string>; setAttribute(): void; querySelector(): unknown }>();
  const node = (id: string) => {
    if (!nodes.has(id)) nodes.set(id, { textContent: "", innerHTML: "", style: {}, setAttribute() {}, querySelector() { return node(`${id}-child`); } });
    return nodes.get(id)!;
  };
  const state = { workspace: { name: "Example business" }, view: ["pending", "granted"].includes(status) ? "invite" : "actions", invitation: { email: "collaborator@example.test", status } };
  const context = {
    state, $: node, document: { documentElement: { lang: "" } }, previewLanguage: language,
    invoiceSurface: false, whatsappSurface: false, reviewOnly: false, registryTimer: undefined, registryVersion: 0,
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
    assert.equal(state.invitation.status, "pending");
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
    assert.equal(state.invitation.status, "granted");
  });
}
