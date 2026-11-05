import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { TABLET_MIN_WIDTH_PX } from "@/lib/responsive-layout";
import en from "@/public/locales/en/common.json";
import es from "@/public/locales/es-419/common.json";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") {
    return new Response(null, { status: 404 });
  }
  const review = new URL(request.url).searchParams;
  const font = review.get("asset") === "inter" ? "InterVariable.woff2"
    : review.get("asset") === "heading" ? "SpaceGrotesk[wght].woff2" : null;
  if (font) {
    const bytes = await readFile(resolve(process.cwd(), "app/fonts", font));
    return new Response(bytes, { headers: { "Content-Type": "font/woff2", "Cache-Control": "no-store" } });
  }
  if (review.get("asset") === "qr") {
    const script = await readFile(resolve(process.cwd(), "../temp/home-setup/qr-preview.js"), "utf8");
    return new Response(script, { headers: { "Content-Type": "text/javascript; charset=utf-8", "Cache-Control": "no-store" } });
  }
  if (review.get("asset") === "invoicing") {
    const script = await readFile(resolve(process.cwd(), "../temp/home-setup/invoicing.js"), "utf8");
    return new Response(script, { headers: { "Content-Type": "text/javascript; charset=utf-8", "Cache-Control": "no-store" } });
  }
  const mobileReview = review.get("viewport") === "mobile";
  const darkReview = review.get("theme") === "dark";
  const sketch = await readFile(resolve(process.cwd(), "../temp/home-setup/index.html"), "utf8");
  const invoiceStyles = await readFile(resolve(process.cwd(), "../temp/home-setup/invoicing.css"), "utf8");
  const styling = `<style>@layer components {
    ${invoiceStyles}
    html,body{margin:0;background:transparent;overflow:hidden}
    html.standalone-preview,html.standalone-preview body{overflow:auto}
    .review,.rail,.bottomnav,.notice{display:none!important}
    .stage,.app,.shell,.workspace{display:block;width:100%;height:auto;min-height:0;max-width:none;padding:0;border:0;border-radius:0;overflow:visible}
    .app{--surface:#fff;container-type:inline-size}.app.dark{--surface:#1f2225;--ink:#fff;--muted:rgba(255,255,255,.7);--line:rgba(255,255,255,.12)}
    .workspace>:not(.setup):not(.completion):not(.preview-tools){display:none!important}
    .setup{margin:0}.completion:empty{display:none}.completion{margin:12px 0}
    .field input,.field select{font-size:16px}
    ${mobileReview ? ".stage{width:390px;max-width:100%;margin:0}" : ""}
  }</style>`;
  const bridge = `<script>
    addEventListener('pointerdown',()=>parent.postMessage({type:'workspace-preview-pointerdown'},location.origin),true);
    addEventListener('keydown',event=>{if(event.key==='Escape'&&!event.defaultPrevented&&new URLSearchParams(location.search).has('surface'))parent.postMessage({type:'workspace-preview-close-dossier'},location.origin)});
    if(parent===window)document.documentElement.classList.add('standalone-preview');
    const syncLocalViewport=()=>{if(parent===window)document.getElementById('app').classList.toggle('is-mobile',innerWidth<${TABLET_MIN_WIDTH_PX})};
    syncLocalViewport();addEventListener('resize',syncLocalViewport);
    if(${mobileReview})document.getElementById("app").classList.add("is-mobile");
    if(${darkReview})document.getElementById("app").classList.add("dark");
    const notifySize=()=>parent.postMessage({type:'workspace-preview-height',height:Math.ceil(document.querySelector('.stage').getBoundingClientRect().height)},location.origin);
    new ResizeObserver(notifySize).observe(document.querySelector('.stage'));
    new MutationObserver(()=>parent.postMessage({type:'workspace-preview-render'},location.origin)).observe(document.getElementById('guidecontent'),{childList:true,subtree:true});
    addEventListener('message',event=>{
      if(event.source!==parent||event.origin!==location.origin||event.data?.type!=='workspace-preview-theme')return;
      if(event.data.context)applyBusinessContext(event.data.context);
      if(typeof event.data.language==='string'&&previewLanguage!==event.data.language){previewLanguage=event.data.language;render()}
      document.getElementById('app').classList.toggle('dark',event.data.dark);
      if(typeof event.data.surface==='string')document.getElementById('app').style.setProperty('--surface',event.data.surface);
      document.getElementById('app').classList.toggle('is-mobile',Boolean(event.data.mobile));
      if(typeof event.data.font==='string')document.body.style.fontFamily=event.data.font;
      notifySize();
    });
    parent.postMessage({type:'workspace-preview-ready'},location.origin);
    notifySize();
  </script>`;
  return new Response(sketch
    .replace("cuadrao-home-setup-mock-v4", "cuadrao-inline-workspace-preview-v1")
    .replace("<script>", `<script>window.workspacePreviewLocales=${JSON.stringify({en:en.workspace_setup_preview,"es-419":es.workspace_setup_preview})}</script><script src="/design-workspace/card?asset=qr"></script><script src="/design-workspace/card?asset=invoicing"></script><script>`)
    .replace("<style>", "<style>@layer theme,base,components,utilities;@layer components {")
    .replace("</style>", `}</style>${styling}`)
    .replace("</html>", `${bridge}</html>`), {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}
