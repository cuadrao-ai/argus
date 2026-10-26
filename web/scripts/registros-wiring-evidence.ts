import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, type Browser, type Page } from "@playwright/test";
import { installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import { reportRequestSchema } from "../lib/business-reports-api";
import { fixtureId } from "../__tests__/fixtures/business-report-http-fixture";
const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
assert.equal(head, process.env.EVIDENCE_EXPECTED_HEAD ?? head);
const evidence = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/registros-wiring-evidence");
const frontend = head;
const backend = "synthetic-contract-fixture-only";
const baseUrl = process.env.EVIDENCE_WEB_BASE_URL ?? "http://127.0.0.1:4395";
const fixtureUrl = process.env.EVIDENCE_FIXTURE_BASE_URL ?? "http://127.0.0.1:4396";
assert.equal(new URL(baseUrl).hostname, "127.0.0.1"); assert.equal(new URL(fixtureUrl).hostname, "127.0.0.1");
assert.equal(process.env.NEXT_PUBLIC_MOCK_AUTH, "true"); mkdirSync(evidence, { recursive: true });
const errors: string[] = [];
const INITIAL_READY_TIMEOUT_MS = 30_000;
async function localBrowser() { return chromium.launch({ headless: true }); }
async function matrix(browser: Browser) {
const records=[];
for(const width of [1440,834,390]) for(const language of ['es-419','en'] as const) for(const theme of ['light','dark'] as const){
 const errors:string[]=[];
 const context=await browser.newContext({viewport:{width,height:1000},hasTouch:width<1024,locale:language==='en'?'en-US':'es-DO',colorScheme:theme});
 await context.route("**/*", route => { const origin = new URL(route.request().url()).origin; if (origin === baseUrl || origin === fixtureUrl) return route.fallback(); errors.push(`blocked ${origin}`); return route.abort(); });const page=await context.newPage(); const calls: { status: number; request: unknown; answer: Record<string, unknown> | null }[]=[];
 page.on('pageerror',error=>errors.push(String(error)));
 page.on('response',async response=>{if(response.url().includes('/business/reports/query'))calls.push({status:response.status(),request:response.request().postDataJSON(),answer:await response.json().catch(()=>null)});});
 await page.route('**/*',route=>{const url=new URL(route.request().url());return ['127.0.0.1','localhost'].includes(url.hostname)||['data:','blob:'].includes(url.protocol)?route.fallback():route.abort();});
 await installBreakpointFixture(page,{language,theme,emptyChat:true,consent:'accepted'});
 await page.addInitScript(({language,theme})=>{localStorage.setItem('cuadrao-business-preview-language',language);localStorage.setItem('argus-theme',theme);},{language,theme});
 await page.route('**/api/v1/business/**',route=>route.continue());
 const report=reportRequestSchema.parse({schema_version:2,filters:{period:{kind:'all'}},sort:'date_asc'});
 const url=new URL(`${baseUrl}/biz`); url.searchParams.set('view','transactions');url.searchParams.set('report',JSON.stringify(report));url.searchParams.set('report_scope',`breakpoint-user:${fixtureId(3000)}`);
 await page.goto(url.href,{waitUntil:'domcontentloaded'});
 await page.locator('[data-report-schema="2"] [data-testid="records-count"]').waitFor();
 await page.waitForTimeout(100);
 const heading=await page.getByRole('heading',{name:language==='en'?'Records':'Registros',exact:true}).count();
 const root=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,language:document.documentElement.lang,dark:document.documentElement.classList.contains('dark')}));
 const exact=await page.locator('[data-testid="transacciones-records"]').innerText();
 if(!heading||root.dark !== (theme === 'dark')||root.scroll>width||!exact.includes('9,007,199,254,740,993.01')||errors.length)throw new Error(JSON.stringify({width,language,theme,heading,root,errors,exact:exact.slice(0,500)}));
 await page.keyboard.press('Tab');const focused=await page.evaluate(()=>({tag:document.activeElement?.tagName,visible:!!document.activeElement?.getBoundingClientRect().width}));
 await page.screenshot({path:`${evidence}/final-${width}-${language}-${theme}.png`,fullPage:true});
 const tableRow = page.locator('tbody tr').first();
 if (await tableRow.count()) { await tableRow.focus(); await page.keyboard.press('ArrowDown'); assert.equal(await page.locator('tbody tr').nth(1).evaluate(node => node === document.activeElement), true); }
 else { await page.keyboard.press('Tab'); assert.equal(await page.evaluate(() => document.activeElement instanceof HTMLButtonElement || document.activeElement instanceof HTMLInputElement), true); }
 let privacy: Record<string, unknown> | null = null;
 if (language === 'es-419' && theme === 'light') {
   await page.locator('[data-testid="amounts-toggle"]').click();
   privacy = await page.locator('.cuadrao-amount').first().evaluate(node => { const style = getComputedStyle(node); return { hidden: document.documentElement.dataset.amountsHidden, color: style.color, shadow: style.textShadow, selection: style.userSelect }; });
   assert.equal(privacy.hidden, 'true'); assert.equal(privacy.color, 'rgba(0, 0, 0, 0)'); assert.equal(privacy.selection, 'none');
   await page.screenshot({path:`${evidence}/final-privacy-${width}.png`,fullPage:true});
   await page.locator('[data-testid="amounts-toggle"]').click();
 }

 records.push({frontend,backend,width,language,theme,root,errors,focused,privacy,query:calls.map(({status,request,answer})=>({status,request,matching_count:answer?.matching_count,page:answer?.page,page_size:answer?.page_size,page_count:answer?.page_count,coverage_notes:answer?.coverage_notes}))});
 await context.close();
}
writeFileSync(`${evidence}/${frontend==='uncommitted-exploratory'?'exploratory':'final'}-browser-matrix.json`,JSON.stringify(records,null,2));
console.log(JSON.stringify({captures:records.length,frontend,backend}));
}

async function recordFlowFailure(page: Page, error: unknown, step: string, calls: readonly unknown[], errors: readonly string[], requests: readonly unknown[] = []) {
  const original = error instanceof Error ? { name: error.name, message: error.message, stack: error.stack } : { message: String(error) };
  writeFileSync(`${evidence}/flow-original-error.json`, JSON.stringify({ head, step, original, url: page.url(), closed: page.isClosed(), calls, errors, requests }, null, 2));
  console.error("Original flows failure", error);
  const diagnostics: string[] = [];
  try { writeFileSync(`${evidence}/flow-body.txt`, await page.locator("body").innerText({ timeout: 1000 })); }
  catch (failure) { diagnostics.push(`body: ${String(failure)}`); }
  try { await page.screenshot({ path: `${evidence}/flow-failure.png`, fullPage: true, timeout: 2000 }); }
  catch (failure) { diagnostics.push(`screenshot: ${String(failure)}`); }
  writeFileSync(`${evidence}/flow-diagnostic-errors.json`, JSON.stringify(diagnostics, null, 2));
}

async function flows(browser: Browser) {
const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});await context.route("**/*", route => { const origin = new URL(route.request().url()).origin; if (origin === baseUrl || origin === fixtureUrl) return route.fallback(); errors.push(`blocked ${origin}`); return route.abort(); });const page=await context.newPage();
page.setDefaultTimeout(10000);
let flowStep = 'setup';
let originalFlowError: unknown;
const requests: { kind: string; url: string; failure?: string }[] = [];
page.on('request', request => requests.push({ kind: 'request', url: request.url() }));
page.on('requestfailed', request => requests.push({ kind: 'failed', url: request.url(), failure: request.failure()?.errorText }));
const calls: { url: string; status: number; method: string; body: string | null; headers: Record<string, string> }[]=[], errors:string[]=[];page.on('pageerror',e=>errors.push(String(e)));page.on('response',async r=>{if(r.url().includes('/business/'))calls.push({url:r.url(),status:r.status(),method:r.request().method(),body:r.request().postData(),headers:r.request().headers()});});
const control=async(body:object)=>{const r=await fetch(`${fixtureUrl}/__fixture/control`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error('control');};
try{
 await installBreakpointFixture(page,{language:'es-419',theme:'light',emptyChat:true,consent:'accepted'});await page.addInitScript(()=>localStorage.setItem('cuadrao-business-preview-language','es-419'));await page.route('**/api/v1/business/**',r=>r.continue());
 const report=reportRequestSchema.parse({schema_version:2,filters:{period:{kind:'all'}},sort:'date_asc'}),url=new URL(`${baseUrl}/biz`);url.searchParams.set('view','transactions');url.searchParams.set('report',JSON.stringify(report));url.searchParams.set('report_scope',`breakpoint-user:${fixtureId(3000)}`);
 flowStep = 'navigate'; await page.goto(url.href,{waitUntil:'domcontentloaded',timeout:INITIAL_READY_TIMEOUT_MS});
 flowStep = 'report-ready'; await page.locator('[data-testid="records-count"]').waitFor({timeout:INITIAL_READY_TIMEOUT_MS});
 console.log('loaded'); flowStep = 'pagination';
 await page.getByRole('button',{name:'Última página',exact:true}).click();await page.locator('[data-testid="records-pagination"][data-page="6"]').waitFor();
 flowStep = 'search'; await page.locator('input[type="search"]').fill('pena');await page.waitForFunction(()=>document.querySelector('[data-testid="records-count"]')?.textContent?.includes('1 de 1'));await page.getByText('José Peña',{exact:true}).waitFor();
 await page.locator('input[type="search"]').fill('');await page.waitForFunction(()=>document.querySelectorAll('tbody tr').length===25);
 flowStep = 'save-view'; await page.getByRole('button',{name:'Vistas',exact:true}).click();await page.getByRole('button',{name:'Guardar vista',exact:true}).click();await page.locator('input[maxlength="120"]').fill('Vista HTTP');await page.getByRole('button',{name:'Guardar',exact:true}).click();await page.locator('input[maxlength="120"]').waitFor({state:'hidden'});
 console.log('view saved');
 flowStep = 'note-replay'; await control({noteUncertain:true});console.log('note control');await page.locator(`[data-record-note="draft:${fixtureId(1)}"]`).click();await page.locator('textarea').fill('Nota durable HTTP 🟢');await page.getByRole('button',{name:'Guardar',exact:true}).click();await page.getByRole('button',{name:'Reintentar',exact:true}).waitFor();await page.screenshot({path:`${evidence}/${frontend}-note-uncertain.png`});await page.getByRole('button',{name:'Reintentar',exact:true}).click();await page.locator('textarea').waitFor({state:'hidden'});
 console.log('note replayed');
 flowStep = 'supporting-replay'; await control({fileUncertainAt:1});await page.locator(`[data-record-attachment="draft:${fixtureId(1)}"]`).click();await page.locator('input[type="file"]').setInputFiles([{name:'apoyo-uno.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic first original bytes')},{name:'apoyo-dos.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic second original bytes')}]);await page.locator('[data-local-files] li').nth(1).waitFor();await page.getByRole('button',{name:'Guardar',exact:true}).click();await page.getByRole('button',{name:'Reintentar',exact:true}).waitFor();await page.getByRole('button',{name:'Reintentar',exact:true}).click();await page.getByRole('dialog').waitFor({state:'hidden'});
 console.log('files replayed');
 flowStep = 'source-download'; await page.locator(`[data-record-attachment="draft:${fixtureId(1)}"]`).click();const bytesDownload=page.waitForEvent('download');await page.getByRole('button',{name:'apoyo-uno.pdf',exact:true}).click();const bytes=await bytesDownload;await bytes.saveAs(`${evidence}/${frontend}-supporting-original.pdf`);if(await (await import("node:fs/promises")).readFile(`${evidence}/${frontend}-supporting-original.pdf`, "utf8")!=='synthetic first original bytes')throw new Error('wrong source bytes');await page.getByRole('dialog').getByRole('button',{name:'Cerrar',exact:true}).click();
 console.log('source bytes correct');
 flowStep = 'export-refresh'; await control({exportChanged:true});await page.locator('[data-testid="add-menu-more"]').click();await page.getByRole('menuitem',{name:'Exportar registros',exact:true}).click();await page.getByRole('alert').filter({hasText:'cambiaron'}).waitFor();await page.screenshot({path:`${evidence}/${frontend}-export-changed.png`});const failedExports=calls.filter(c=>c.url.endsWith('/reports/export'));if(failedExports.length!==1)throw new Error('silent retry');await control({exportChanged:false});await page.getByRole('button',{name:'Actualizar',exact:true}).click();await page.locator('[data-testid="records-count"]').waitFor();
 flowStep = 'export-download'; await page.locator('[data-testid="add-menu-more"]').click();const zipDownload=page.waitForEvent('download');await page.getByRole('menuitem',{name:'Exportar registros',exact:true}).click();const zip=await zipDownload;await zip.saveAs(`${evidence}/${frontend}-contract-download.bin`);
 const notes=calls.filter(c=>c.url.endsWith('/current-note'));const files=calls.filter(c=>c.url.endsWith('/supporting-files'));if(notes.length!==2||notes[0].headers['idempotency-key']!==notes[1].headers['idempotency-key']||notes[0].body!==notes[1].body||files.length!==3||files[0].headers['idempotency-key']!==files[1].headers['idempotency-key']||files[0].headers['x-draft-version']!==files[1].headers['x-draft-version']||files[2].headers['x-draft-version']===files[1].headers['x-draft-version']||errors.length)throw new Error(JSON.stringify({notes,files,errors}));
 writeFileSync(`${evidence}/${frontend}-browser-flows.json`,JSON.stringify({frontend,backend:backend,proof:'synthetic contract HTTP only; no backend/database acceptance',calls,errors},null,2));console.log({notes:notes.length,files:files.length,exports:calls.filter(c=>c.url.endsWith('/reports/export')).length,errors});
} catch (error) {
  originalFlowError = error;
  try { await recordFlowFailure(page, error, flowStep, calls, errors, requests); }
  catch (failure) { console.error("Failure diagnostics unavailable", failure); }
  throw error;
} finally {
  try { await context.close(); }
  catch (failure) { if (originalFlowError) console.error("Cleanup after original flows failure", failure); else throw failure; }
}
}

async function recovery(browser: Browser) {
const proofs: Record<string, unknown>[]=[];
const control=async(body:object)=>{await fetch(`${fixtureUrl}/__fixture/control`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});};
async function screen(report?:object){const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();await context.route("**/*", route => { const origin = new URL(route.request().url()).origin; if (origin === baseUrl || origin === fixtureUrl) return route.fallback(); errors.push(`blocked ${origin}`); return route.abort(); });page.setDefaultTimeout(10000);await installBreakpointFixture(page,{language:'es-419',theme:'light',emptyChat:true,consent:'accepted'});await page.addInitScript(()=>localStorage.setItem('cuadrao-business-preview-language','es-419'));await page.route('**/api/v1/business/**',r=>r.continue());const url=new URL(`${baseUrl}/biz?view=transactions`);if(report){url.searchParams.set('report',JSON.stringify(reportRequestSchema.parse(report)));url.searchParams.set('report_scope',`breakpoint-user:${fixtureId(3000)}`);}await page.goto(url.href,{waitUntil:'domcontentloaded',timeout:INITIAL_READY_TIMEOUT_MS});return {page,context};}
try{
await control({legacy:false,queryError:false});
let {page,context}=await screen({schema_version:2,filters:{period:{kind:'all'},record_families:['sale']}});await page.locator('[data-testid="records-results-summary"]').waitFor({timeout:INITIAL_READY_TIMEOUT_MS});if(await page.locator('[data-testid="records-results-summary"] .cuadrao-amount').count())throw new Error('synthetic amount');await page.getByText('Monto no disponible.',{exact:true}).waitFor();await page.screenshot({path:`${evidence}/${frontend}-pending-amounts.png`});proofs.push({case:'automatic-amount-cards-unknown',knownAmounts:0});await context.close();
await control({legacy:true});({page,context}=await screen());await page.locator('[data-report-schema="1"] [data-testid="records-count"]').waitFor({timeout:INITIAL_READY_TIMEOUT_MS});await page.screenshot({path:`${evidence}/${frontend}-v1-fallback.png`});proofs.push({case:'v1-query-usable',schema:1,overviewDisabled:await page.locator('[data-overview-filter]:disabled').count()});await context.close();
await control({legacy:false,queryError:true});({page,context}=await screen());await page.locator('[data-testid="error-reference"]').waitFor({timeout:INITIAL_READY_TIMEOUT_MS});const reference=await page.locator('[data-reference-short]').innerText(),body=await page.locator('body').innerText();if(reference.includes('12345678-1234')||body.includes('INTERNAL_FIXTURE_SECRET_NOT_FOR_UI'))throw new Error('private failure leaked');await page.screenshot({path:`${evidence}/${frontend}-reference-recovery.png`});await control({queryError:false});await page.getByRole('button',{name:'Actualizar',exact:true}).click();await page.locator('[data-testid="records-count"]').waitFor();proofs.push({case:'query-error-short-reference-and-refresh',reference});await context.close();
({page,context}=await screen({schema_version:2,filters:{period:{kind:'all'}}}));await page.locator('[data-testid="records-count"]').waitFor({timeout:INITIAL_READY_TIMEOUT_MS});await page.getByRole('button',{name:'Vistas',exact:true}).click();const viewName=await page.getByRole('button',{name:'Vista HTTP',exact:true}).count();if(!viewName)throw new Error('run main flows before recovery');await page.getByRole('button',{name:'Renombrar',exact:true}).first().click();await page.locator('input[maxlength="120"]').fill('Nombre pendiente HTTP');await control({bumpViewVersion:true});await page.getByRole('button',{name:'Guardar',exact:true}).click();await page.getByRole('alert').filter({hasText:'vista cambió'}).waitFor();await page.screenshot({path:`${evidence}/${frontend}-view-version-conflict.png`});if(await page.locator('input[maxlength="120"]').inputValue()!=='Nombre pendiente HTTP')throw new Error('draft lost');await page.getByRole('button',{name:'Actualizar',exact:true}).click();await page.waitForTimeout(100);await page.getByRole('button',{name:'Guardar',exact:true}).click();await page.locator('input[maxlength="120"]').waitFor({state:'hidden'});proofs.push({case:'view-version-conflict-explicit-readback-preserves-draft'});await context.close();
writeFileSync(`${evidence}/${frontend}-browser-recovery.json`,JSON.stringify({frontend,backend:backend,proofs},null,2));console.log(proofs);
}finally{await control({legacy:false,queryError:false});}
}
let browser: Browser | undefined;
let stage = "launch";
let browserClosed = false;
try {
  browser = await localBrowser();
  stage = "matrix"; await matrix(browser);
  stage = "flows"; await flows(browser);
  stage = "recovery"; await recovery(browser);
  assert.deepEqual(errors, []); stage = "complete";
} catch (error) {
  errors.push(`${stage}: ${String(error)}`); throw error;
} finally {
  try { await browser?.close(); browserClosed = true; }
  finally { writeFileSync(`${evidence}/source.json`, JSON.stringify({ head, proof: "synthetic contract HTTP fixture", backend: null, stage, browserClosed, errors }, null, 2)); }
}
