import {chromium,expect} from "../../web/node_modules/@playwright/test/index.mjs";
import {spawn,execFileSync} from "node:child_process";
import {createHash} from "node:crypto";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {openSync,closeSync} from "node:fs";
import {dirname,resolve,join} from "node:path";
import {fileURLToPath} from "node:url";
if(!globalThis.Bun)throw new Error("Run with the pinned Bun runtime");
const root=resolve(dirname(fileURLToPath(import.meta.url)),"../..");
const argument=(name,fallback)=>{const index=process.argv.indexOf(name);return index<0?fallback:process.argv[index+1];};
const webPort=Number(argument("--web-port","4411")),fixturePort=Number(argument("--fixture-port","4412"));
if(![webPort,fixturePort].every(port=>Number.isInteger(port)&&port>1023&&port<65536)||webPort===fixturePort)throw new Error("Use two distinct local ports");
const webOrigin="http://127.0.0.1:"+webPort,fixtureOrigin="http://127.0.0.1:"+fixturePort;
const output=resolve(root,argument("--output","temp/business-client-wiring-evidence"));
await mkdir(output,{recursive:true});
const sourceHead=execFileSync("git",["rev-parse","HEAD"],{cwd:root,encoding:"utf8"}).trim();
const sourceDirty=execFileSync("git",["status","--porcelain","--untracked-files=no"],{cwd:root,encoding:"utf8"}).trim();
if(sourceDirty&&!process.argv.includes("--allow-dirty"))throw new Error("Commit the source before capturing exact-head evidence");
const unexpectedWrites=[];
const allowedWrite=(method,path)=>[
 /^POST \/business\/space\/name-prompt$/,
 /^POST \/business\/spaces$/,
 /^PATCH \/business\/spaces\/[^/]+\/profile$/,
 /^POST \/business\/spaces\/[^/]+\/appearance\/assets$/,
 /^PATCH \/business\/fiscal-profile$/,
 /^POST \/business\/access\/invitations$/,
 /^PATCH \/business\/access\/grants\/[^/]+$/,
 /^DELETE \/business\/access\/(grants|invites)\/[^/]+$/,
 /^POST \/business\/invitations\/[^/]+\/accept$/,
].some(pattern=>pattern.test(method+" "+path));

import { createFixtureBusinessDataSource } from "../../web/components/business-app/fixture-data.ts";
const source = createFixtureBusinessDataSource({ chatAvailable: false });
const ids = ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"];
const grants = ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"];
const permissions = ["read", "prepare", "approve", "manage", "download", "export", "assign_owner"];
const profiles = new Map(ids.map((id, index) => [id, { space_id: id, name: index ? "Taller Sol" : "Colmado Luna", country: "DO", currency: "DOP", revision: 1, details: { address: index ? "Calle Sol 8" : "Calle Luna 12", province: "Distrito Nacional", municipality: "Santo Domingo", email: "contacto@example.test", phone: "809 555 0100", website: "https://negocio.example.test", description: "Negocio de muestra" }, appearance: { kind: "avatar", token: index ? "gold" : "teal", mark: "initials" }, image: null }]));
const access = { grants: [{ id: grants[0], email: "pilot@example.test", display_name: "José de muestra", business_role: "owner", permissions, owner: true, capabilities: ["read", "prepare", "approve"], created_at: "2026-10-01T12:00:00Z" }, { id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", email: "equipo@example.test", display_name: "Persona de muestra", business_role: "editor", permissions: ["read", "prepare", "download", "export"], owner: false, capabilities: ["read", "prepare"], created_at: "2026-10-02T12:00:00Z" }], invites: [] };
let invitations = [{ id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", space_id: "44444444-4444-4444-8444-444444444444", name: "Taller Invitado", requested_role: "admin", expires_at: "2026-11-02T12:00:00Z" }];
let config = { profileRefused:false,refuseInvitation:false,accessRefreshFailure:false, profileFailure: false, conflict: false, appearanceFailure: false, role: "owner", acceptFailure: false };
let creates = 0;
const history = [];
const receipts = new Map;
const images = new Map;
const headers = { "Access-Control-Allow-Origin": webOrigin, "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Business-Grant,Idempotency-Key,X-Argus-Client-Capabilities", "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS", "Content-Type": "application/json" };
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers });
const server = Bun.serve({ hostname: "127.0.0.1", port: fixturePort, async fetch(request) {
  const url = new URL(request.url), path = url.pathname.replace(/^\/api\/v1/, "");
  if (request.method === "OPTIONS")
    return new Response(null, { status: 204, headers });
  const selected = request.headers.get("X-Business-Grant");
  const index = grants.indexOf(selected ?? "");
  const id = ids[index < 0 ? 0 : index];
  const current = profiles.get(id);
  if (path === "/__qa" && request.method === "POST") {
    config = { ...config, ...await request.json() };
    return json({ ok: true });
  }
  if (path === "/__qa")
    return json({ config, creates, history, profiles: [...profiles.values()] });
  if (!["GET", "HEAD"].includes(request.method) && !allowedWrite(request.method, path)) {
    unexpectedWrites.push({ method: request.method, path });
    return json({ code: "unexpected_synthetic_write" }, 500);
  }
  history.push({ path, method: request.method, grant: selected, key: request.headers.get("Idempotency-Key"), hasAuthorization: request.headers.has("Authorization"), hasCookie: request.headers.has("Cookie") });
  if (path.startsWith("/assets/")) {
    const bytes = images.get(path.split("/").at(-1));
    return bytes ? new Response(bytes.body, { headers: { ...headers, "Content-Type": bytes.type } }) : json({}, 404);
  }
  if (path.endsWith("/appearance/assets")) {
    const asset = "local-image-asset";
    images.set(asset, {body:await request.arrayBuffer(),type:request.headers.get("Content-Type")??"image/webp"});
    return json({ asset_id: asset, width: 64, height: 32, source_url: fixtureOrigin + "/assets/" + asset, rendered_url: null });
  }
  if (path === "/me")
    return json({ user: { id: "mock-auth-user", email: "pilot@example.test", username: null, display_name: "José de muestra", preferred_name: "José", language: "es-419", locale: "es-419", country: "DO", currency: "DOP", avatar_theme: "teal", onboarding: { completed: true, stage: "completed", language_confirmed: true, primary_goal: null } }, account_kind: "registered", guest: null, capabilities: { can_manage_account: true, can_submit_feedback: true, can_create_additional_conversation: true, can_manage_conversation: true, can_save_decision: true, can_use_omnisearch: true, can_search_current_workspace: true, can_use_grounded_discovery: false }, public_account_access_enabled: true });
  if (path === "/me/usage")
    return json({});
  if (path === "/conversations")
    return json({ items: [], next_cursor: null });
  if (path === "/business/consent")
    return json({ version: url.searchParams.get("version"), accepted_at: "2026-10-01T12:00:00Z" });
  if (path === "/business/spaces" && request.method === "POST") {
    const key = request.headers.get("Idempotency-Key");
    if (receipts.has(key))
      return json(receipts.get(key));
    const body = await request.json();
    const nextId = "33333333-3333-4333-8333-333333333333", grant = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
    ids.push(nextId);
    grants.push(grant);
    profiles.set(nextId, { ...current, space_id: nextId, name: body.name, country: body.country, revision: 0, details: { address: "", province: "", municipality: "", email: "", phone: "", website: "", description: "" }, appearance: { kind: "default" }, image: null });
    const value = { id: nextId, name: body.name, country: body.country, currency: "DOP", logo_url: null };
    receipts.set(key, value);
    creates++;
    return json(value, 201);
  }
  if (path === "/business/spaces")
    return json({ spaces: ids.map((id, index) => ({ space_id: id, name: profiles.get(id).name, grant_id: grants[index], role: config.role === "viewer" || id === "44444444-4444-4444-8444-444444444444" ? "accountant" : "owner", business_role: config.role === "viewer" ? "viewer" : id === "44444444-4444-4444-8444-444444444444" ? "admin" : "owner", permissions: config.role === "viewer" ? ["read"] : id === "44444444-4444-4444-8444-444444444444" ? ["read", "prepare", "manage", "download", "export"] : permissions, capabilities: config.role === "viewer" ? ["read"] : id === "44444444-4444-4444-8444-444444444444" ? ["read", "prepare"] : ["read", "prepare", "approve"], access_seen: true })), closed_spaces: [] });
  const match = path.match(/^\/business\/spaces\/([^/]+)\/profile$/);
  if (match) {
    if(config.profileRefused)return json({code:"business_permission_denied"},403);
    if (config.profileFailure)
      return json({ code: "profile_unavailable", request_id: "fixture-profile" }, 503);
    const saved = profiles.get(match[1]);
    if (!saved)
      return json({ code: "business_record_not_found" }, 404);
    if (request.method === "PATCH") {
      if (config.role === "viewer")
        return json({ code: "business_permission_denied" }, 403);
      const body = await request.json();
      if (config.conflict) {
        config.conflict = false;
        saved.revision++;
        return json({ code: "business_workspace_stale" }, 409);
      }
      if (body.appearance && config.appearanceFailure) {
        config.appearanceFailure = false;
        return json({ code: "image_storage_unavailable" }, 503);
      }
      const key = request.headers.get("Idempotency-Key");
      if (receipts.has(key))
        return json(saved);
      if (body.expected_revision !== saved.revision)
        return json({ code: "business_workspace_stale" }, 409);
      Object.assign(saved, { ...body, name: body.name ?? saved.name, details: { ...saved.details, ...body.details }, appearance: body.appearance ?? saved.appearance, revision: saved.revision + 1 });
      if (body.appearance?.kind === "image")
        saved.image = { asset_id: body.appearance.asset_id, width: 64, height: 32, source_url: fixtureOrigin + "/assets/" + body.appearance.asset_id, rendered_url: fixtureOrigin + "/assets/" + body.appearance.asset_id };
      delete saved.expected_revision;
      receipts.set(key, true);
    }
    return json(config.role==="viewer"&&saved.image?{...saved,image:{...saved.image,source_url:null}}:saved);
  }
  if (path === "/business/space")
    return json({ id: current.space_id, name: current.name, country: current.country, currency: current.currency, logo_url: null });
  if (path.includes("/business/space/name"))
    return json({ id: current.space_id, name: current.name, name_required: false, name_prompt_seen: true, show_prompt: false });
  if (path === "/business/fiscal-profile")
    return json({ name: current.name, tax_id: { type: "rnc", value: "131245678" }, can_edit: config.role !== "viewer" });
  if (path === "/business/workspace")
    return json(await source.workspace());
  if (path === "/business/overview")
    return json(await source.overview("2026-10-01", "2026-10-31"));
  if (path === "/business/receipts")
    return json(await source.receiptPage("inbox"));
  if (path === "/business/receipt-activity")
    return json(await source.receiptActivity());
  if (path === "/business/captures")
    return json({ items: [], has_more: false });
  if (path === "/business/email/deliveries")
    return json({ items: [] });
  if (path === "/business/access")
    return config.accessRefreshFailure?json({code:"access_unavailable"},503):json(access);
  if (path === "/business/access/invitations") {
    if(config.refuseInvitation)return json({code:"business_permission_denied"},403);
    const body = await request.json();
    return json({ results: body.recipients.map((recipient) => {
      const invite = { id: crypto.randomUUID(), email: recipient.email, requested_role: recipient.role, state: "pending", created_at: "2026-10-26T12:00:00Z", expires_at: "2026-11-02T12:00:00Z" };
      access.invites.push(invite);
      return { command_key: recipient.command_key, email: recipient.email, invite_id: invite.id, state: "pending", delivery: "uncertain", code: null };
    }) });
  }
  if (path.startsWith("/business/access/grants/") && request.method === "PATCH") {
    const body = await request.json();
    const person = access.grants.find((person) => person.id === path.split("/").at(-1));
    if (["owner", "admin"].includes(body.role))
      access.invites.push({ id: crypto.randomUUID(), email: person.email, requested_role: body.role, state: "pending", created_at: "2026-10-26T12:00:00Z", expires_at: "2026-11-02T12:00:00Z" });
    else
      person.business_role = body.role;
    return json(access);
  }
  if (path.startsWith("/business/access/") && request.method === "DELETE") {
    const target = path.split("/").at(-1);
    access.grants = access.grants.filter((person) => person.id !== target);
    access.invites = access.invites.filter((invite) => invite.id !== target);
    return new Response(null, { status: 204, headers });
  }
  if (path === "/business/invitations")
    return json(invitations);
  if (path.endsWith("/accept")) {
    if (config.acceptFailure)
      return json({ code: "business_invitation_expired" }, 409);
    const body = await request.json();
    const grant = "ffffffff-ffff-4fff-8fff-ffffffffffff";
    if (!ids.includes(body.space_id)) {
      ids.push(body.space_id);
      grants.push(grant);
      profiles.set(body.space_id, { ...current, space_id: body.space_id, name: "Taller Invitado", details: { ...current.details, address: "Calle Invitada 16" }, revision: 1 });
    }
    invitations = [];
    return json({ space_id: body.space_id, grant_id: grant });
  }
  if (path === "/business/owned-spaces" || path === "/business/closed-spaces")
    return json({ spaces: [] });
  if (path === "/business/search/recents")
    return json({ items: [] });
  return json({ code: "local_fixture_route_unhandled" }, 404);
} });
console.log(`Synthetic HTTP fixtures on ${server.url}`);

const checks=[];
const screenshots=[];
const failures=[];
const errors=[];
let browser;
let app;
let page;
const allowedOrigins=new Set([webOrigin,fixtureOrigin]);
const record=(name)=>{checks.push(name);console.log(`PASS ${name}`);};
const configure=(data)=>fetch(`${fixtureOrigin}/__qa`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
const evidenceState=async()=>(await fetch(`${fixtureOrigin}/__qa`)).json();
async function capture(name){
 await page.evaluate(()=>{if(document.getElementById("synthetic-evidence-label"))return;const label=document.createElement("div");label.id="synthetic-evidence-label";label.textContent="MOCK - local HTTP fixtures";label.style.cssText="position:fixed;top:4px;right:4px;z-index:2147483647;padding:3px 7px;background:#fffefa;color:#172b26;border:1px solid #dce0da;border-radius:4px;font:11px sans-serif;pointer-events:none";document.body.append(label);});
 await page.screenshot({path:join(output,`${name}.png`),fullPage:true});
 screenshots.push(`${name}.png`);
}
async function chooseBusiness(name){
 const trigger=page.locator('[data-testid="business-switcher"] button[aria-haspopup="menu"]');
 await trigger.click();await page.getByRole("menuitem",{name:"Cambiar de negocio",exact:true}).click();await page.getByRole("option",{name:new RegExp(name)}).click();
 await expect(trigger).toHaveAttribute("aria-label",name);
}
async function openSettings(){
 await page.locator('[data-testid="business-switcher"] button[aria-haspopup="menu"]').click();await page.getByRole("menuitem",{name:"Configurar",exact:true}).click();
 await expect(page.getByTestId("business-profile-preview")).toBeVisible();
}
async function addBusiness(){
 await page.locator('[data-testid="business-switcher"] button[aria-haspopup="menu"]').click();await page.getByRole("menuitem",{name:"Añadir negocio",exact:true}).click();
}
async function closeDossier(){
 await page.locator('[data-testid="side-drawer"] button[aria-label="Cerrar"]').click();
}
try{
 const serverLog=openSync(join(output,"server.log"),"w");
 app=spawn(process.execPath,[join(root,"web/node_modules/next/dist/bin/next"),"start","--hostname","127.0.0.1","--port",String(webPort)],{cwd:join(root,"web"),env:{HOME:process.env.HOME??"",PATH:process.env.PATH??"",NEXT_PUBLIC_MOCK_AUTH:"true",NEXT_PUBLIC_BUSINESS_PILOT_ENABLED:"true",NEXT_PUBLIC_ENABLE_SPANISH:"true",NEXT_PUBLIC_CUADRAO_API_URL:`${fixtureOrigin}/api/v1`,NEXT_TELEMETRY_DISABLED:"1"},stdio:["ignore",serverLog,serverLog]});
 closeSync(serverLog);
 const deadline=Date.now()+60000;
 while(true){try{const response=await fetch(webOrigin);if(response.ok)break;}catch{}if(Date.now()>deadline||app.exitCode!==null)throw new Error("Isolated app did not start");await new Promise(resolve=>setTimeout(resolve,300));}
 browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},colorScheme:"light",locale:"es-DO"});
 await context.route("**/*",route=>{const url=new URL(route.request().url());if(["data:","blob:"].includes(url.protocol)||allowedOrigins.has(url.origin))return route.continue();failures.push(`External browser request refused: ${url.origin}`);return route.abort();});
 page=await context.newPage();page.on("pageerror",error=>errors.push(error.message));
 await page.goto(`${webOrigin}/biz?view=business`,{waitUntil:"networkidle"});
 await expect(page.getByTestId("business-profile-preview")).toBeVisible();
 await expect(page.locator('iframe[src*="invoicing"]')).toHaveCount(0);
 await expect(page.getByTestId("business-profile-preview").getByRole("button",{name:"Facturación electrónica",exact:false})).toHaveCount(0);
 record("production profile uses saved HTTP facts without preview activation");
 for(const width of [360,390,768,1024,1280,1440]){
  await page.setViewportSize({width,height:width<768?900:1000});
  await page.waitForTimeout(180);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  expect(overflow).toBe(false);
  if([390,768,1440].includes(width))await capture(`MOCK-profile-${width}`);
 }
 record("profile has no page overflow at six approved widths");
 await page.setViewportSize({width:1440,height:1000});
 await page.getByRole("button",{name:/Ubicación y contacto/}).click();
 await page.getByLabel("Dirección del negocio",{exact:true}).fill("Calle Clara 24");
 await configure({conflict:true});await page.getByRole("button",{name:"Guardar cambios",exact:true}).click();
 await expect(page.getByText("Hay cambios guardados desde que abriste este formulario.",{exact:false})).toBeVisible();
 await expect(page.getByLabel("Dirección del negocio",{exact:true})).toHaveValue("Calle Clara 24");await capture("MOCK-profile-conflict-1440");
 record("version conflict retains the attempted contact edit");
 await page.getByRole("button",{name:"Guardar cambios",exact:true}).click();await expect(page.getByText("Datos guardados.",{exact:true})).toBeVisible();
 await closeDossier();await page.reload({waitUntil:"networkidle"});await expect(page.getByRole("button",{name:/Ubicación y contacto/})).toContainText("Calle Clara 24");
 record("accepted contact save survives full browser reload");
 await chooseBusiness("Taller Sol");await openSettings();await expect(page.getByTestId("business-profile-preview")).toContainText("Calle Sol 8");
 expect((await evidenceState()).history.some(row=>row.path.includes(`${ids[1]}/profile`)&&row.grant===grants[1])).toBe(true);
 record("second Owner Business retains its exact grant");
 await chooseBusiness("Colmado Luna");await openSettings();await page.getByRole("radio",{name:"Acceso",exact:true}).click();
 const members=page.getByTestId("business-access-preview").locator(":scope > ul");
 await expect(members.getByText("equipo@example.test",{exact:true})).toBeVisible();
 for(const width of [390,768,1440]){await page.setViewportSize({width,height:1000});await page.waitForTimeout(180);await capture(`MOCK-access-${width}`);}
 await page.getByRole("combobox",{name:/Acceso de equipo@example.test/}).click();await page.getByRole("option",{name:/Administrador/}).click();
 await expect(page.getByText("Invitación creada. Todavía no tiene acceso; falta que acepte la invitación.",{exact:true})).toBeVisible();
 await expect(members.getByRole("combobox",{name:/Acceso de equipo@example.test/})).toContainText("Editor");
 record("Admin promotion keeps the existing membership pending recipient acceptance");
 await page.getByRole("button",{name:"Invita a un colaborador",exact:true}).click();await page.getByLabel("Correo electrónico",{exact:true}).fill("nueva@example.test");
 await page.getByRole("combobox",{name:/Acceso Editor/}).click();await page.getByRole("option",{name:/Lector/}).click();await page.getByRole("button",{name:"Enviar invitaciones",exact:true}).click();
 await expect(page.getByText("No pudimos confirmar el envío del correo. Revisa su estado antes de volver a intentarlo.",{exact:true})).toBeVisible();await capture("MOCK-invitation-uncertain-1440");
 expect((await evidenceState()).history.filter(row=>row.path==="/business/access/invitations")).toHaveLength(1);
 record("selected Viewer invitation remains pending and uncertain email is not resent");
 await closeDossier();
 await page.getByRole("button",{name:/Quitar.*equipo@example.test/}).click();await page.getByRole("button",{name:"Quitar acceso",exact:true}).click();
 await expect(members.getByText("equipo@example.test",{exact:true})).toHaveCount(0);
 record("revocation waits for 204 and the accepted server list removes membership");
 await page.getByTestId("business-notifications-trigger").click();await page.getByRole("button",{name:"Aceptar invitación",exact:true}).click();
 await expect(page.locator('[data-testid="business-switcher"] button[aria-haspopup="menu"]')).toHaveAttribute("aria-label","Taller Invitado");
 record("recipient acceptance selects only the server-returned grant");
 await addBusiness();await page.getByLabel("Nombre del negocio",{exact:true}).fill("Taller Estrella");await page.getByRole("combobox",{name:/País de operación/}).click();await page.getByRole("option",{name:"República Dominicana",exact:true}).click();
 await page.getByRole("button",{name:"Añadir imagen · Opcional",exact:true}).click();await page.getByRole("button",{name:"Laguna",exact:true}).click();await page.getByRole("button",{name:"Guardar imagen",exact:true}).click();
 await configure({appearanceFailure:true});await page.getByRole("button",{name:"Crear negocio",exact:true}).click();await expect(page.getByText("El negocio se creó, pero no se pudo cargar la imagen.",{exact:true})).toBeVisible();await capture("MOCK-created-image-pending-1440");
 expect((await evidenceState()).creates).toBe(1);
 const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem("cuadrao:business_creation:v1")??"{}"));
 expect(stored["mock-auth-user"].operation.created.id).toBe("33333333-3333-4333-8333-333333333333");expect(JSON.stringify(stored)).not.toContain("data:image");expect(JSON.stringify(stored)).not.toContain("contacto@example.test");
 await page.reload({waitUntil:"networkidle"});await addBusiness();
 await expect(page.getByRole("button",{name:"Reintentar imagen",exact:true})).toBeDisabled();
 await page.getByRole("button",{name:"Añadir imagen · Opcional",exact:true}).click();await page.getByRole("button",{name:"Laguna",exact:true}).click();await page.getByRole("button",{name:"Guardar imagen",exact:true}).click();await page.getByRole("button",{name:"Reintentar imagen",exact:true}).click();
 await expect(page.locator('[data-testid="business-switcher"] button[aria-haspopup="menu"]')).toHaveAttribute("aria-label","Taller Estrella");expect((await evidenceState()).creates).toBe(1);
 expect(await page.evaluate(()=>JSON.parse(localStorage.getItem("cuadrao:business_creation:v1")??"{}")["mock-auth-user"])).toBeUndefined();
 record("reload before confirmed appearance retains the created ID and reselection never creates another Business");
 await chooseBusiness("Colmado Luna");await openSettings();
 await context.addCookies([{name:"fixture_session",value:"synthetic",url:fixtureOrigin}]);await page.getByRole("button",{name:"Cambiar imagen",exact:true}).click();await page.getByRole("radio",{name:"Imagen",exact:true}).click();
 const image=await page.evaluate(()=>{const canvas=document.createElement("canvas");canvas.width=64;canvas.height=32;const paint=canvas.getContext("2d");paint.fillStyle="#2f5a49";paint.fillRect(0,0,64,32);paint.fillStyle="#8fcbb0";paint.fillRect(8,8,48,16);return canvas.toDataURL("image/png");});
 await page.locator('input[type="file"]').setInputFiles({name:"identidad-muestra.png",mimeType:"image/png",buffer:Buffer.from(image.split(",")[1],"base64")});await page.getByRole("button",{name:"Usar imagen",exact:true}).click();await page.getByRole("button",{name:"Guardar imagen",exact:true}).click();
 await expect(page.locator('[data-testid="business-profile-preview"] img[src^="data:image/"]')).toBeVisible();
 const assetReads=(await evidenceState()).history.filter(row=>row.path.startsWith("/assets/"));expect(assetReads.length).toBeGreaterThan(0);expect(assetReads.every(row=>!row.hasAuthorization&&!row.hasCookie)).toBe(true);
 record("bounded saved-image reads render under CSP without forwarding API credentials or cookies");
 await configure({role:"viewer"});await page.reload({waitUntil:"networkidle"});await chooseBusiness("Colmado Luna");await openSettings();await expect(page.getByTestId("business-profile-preview")).toBeVisible();await expect(page.getByRole("radio",{name:"Acceso",exact:true})).toHaveCount(0);await page.getByRole("button",{name:/Ubicación y contacto/}).click();await expect(page.getByLabel("Dirección del negocio",{exact:true})).toBeDisabled();await expect(page.getByRole("button",{name:"Guardar cambios",exact:true})).toHaveCount(0);await page.setViewportSize({width:390,height:900});await capture("MOCK-viewer-profile-390");
 record("Viewer renders server facts read only without management or activation controls");
 await configure({role:"owner"});await page.reload({waitUntil:"networkidle"});await chooseBusiness("Colmado Luna");await openSettings();await page.setViewportSize({width:1440,height:1000});
 await page.getByRole("button",{name:/Ubicación y contacto/}).click();await page.getByLabel("Dirección del negocio",{exact:true}).fill("Edición privada pendiente");await configure({profileRefused:true});await page.getByRole("button",{name:"Guardar cambios",exact:true}).click();
 await expect(page.getByTestId("business-profile-preview")).toHaveCount(0);await expect(page.getByTestId("side-drawer")).toHaveCount(0);await expect(page.locator('img[src^="data:image/"]')).toHaveCount(0);await expect(page.locator("body")).not.toContainText("contacto@example.test");await capture("MOCK-profile-refused-1440");
 record("definitive profile refusal clears contact fiscal draft and saved image presentation");
 await configure({profileRefused:false});await page.reload({waitUntil:"networkidle"});await chooseBusiness("Colmado Luna");await openSettings();await page.getByRole("radio",{name:"Acceso",exact:true}).click();await expect(page.getByTestId("business-access-preview")).toBeVisible();
 await page.getByRole("button",{name:"Invita a un colaborador",exact:true}).click();await page.getByLabel("Correo electrónico",{exact:true}).fill("privado@example.test");await configure({refuseInvitation:true});await page.getByRole("button",{name:"Enviar invitaciones",exact:true}).click();
 await expect(page.getByTestId("business-access-preview")).toHaveCount(0);await expect(page.getByTestId("side-drawer")).toHaveCount(0);await expect(page.locator("body")).not.toContainText("pilot@example.test");await expect(page.locator("body")).not.toContainText("nueva@example.test");await capture("MOCK-access-refused-1440");
 record("definitive invitation refusal clears loaded membership invitations and the open dialog");
 await configure({refuseInvitation:false});await page.reload({waitUntil:"networkidle"});await chooseBusiness("Colmado Luna");await openSettings();await page.getByRole("radio",{name:"Acceso",exact:true}).click();await page.getByTestId("business-access-preview").locator("summary").click();
 await page.getByRole("button",{name:/Cancelar.*nueva@example.test/}).click();await configure({accessRefreshFailure:true});await page.getByTestId("confirm-dialog-confirm").click();
 await expect(page.getByTestId("business-access-preview")).toHaveCount(0);await expect(page.locator('p[role="alert"]')).toBeVisible();await expect(page.getByRole("button",{name:"Reintentar",exact:true})).toBeVisible();await expect(page.locator("body")).not.toContainText("nueva@example.test");await capture("MOCK-confirmed-removal-refresh-failed-1440");
 record("confirmed 204 removal remains accepted when the followup access refresh fails");
 expect(errors).toEqual([]);expect(failures).toEqual([]);expect(unexpectedWrites).toEqual([]);
}catch(error){
 failures.push(error.stack??String(error));
 if(page){await writeFile(join(output,"failure-body.txt"),await page.locator("body").innerText().catch(()=>"unavailable"));await capture("MOCK-failure").catch(()=>{});}
}finally{
 await browser?.close();app?.kill("SIGTERM");server.stop(true);
 const head=execFileSync("git",["rev-parse","HEAD"],{cwd:root,encoding:"utf8"}).trim();
 if(head!==sourceHead)failures.push("Git head changed during evidence capture");
 const screenshotHashes=Object.fromEntries(await Promise.all(screenshots.map(async name=>[name,createHash("sha256").update(await readFile(join(output,name))).digest("hex")])));
 await writeFile(join(output,"synthetic-evidence.json"),JSON.stringify({head:sourceHead,finishedHead:head,base:"codex/private-alpha-next",synthetic:true,hostedAcceptance:false,sourceDirty:Boolean(sourceDirty),viewportWidths:[360,390,768,1024,1280,1440],checks,failures,errors,unexpectedWrites,screenshotHashes,corsScope:"Local cross-port loopback HTTP only. Hosted storage CORS and auth were not tested.",mockAuthLimit:"Full reload of a UUID Business selection is not proven by mock auth; account-scoped persistence is covered by unit tests."},null,2));
 await writeFile(join(output,"synthetic-http-requests.json"),JSON.stringify(history,null,2));
 if(failures.length){console.error(failures.join("\n"));process.exitCode=1;}else console.log(`Synthetic Business evidence passed: ${checks.length} checks, ${screenshots.length} screenshots, head ${head}`);
}
