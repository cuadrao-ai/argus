export function waitlistResult(title: string, body: string, status = 200, action?: { url: string; label: string }): Response {
  const escape = (value: string) => value.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
  const form = action ? `<form method="post" action="${escape(action.url)}"><button type="submit">${escape(action.label)}</button></form>` : "";
  return new Response(`<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${escape(title)} | Cuadrao</title><style>body{margin:0;background:#f7f7f2;color:#172c26;font:18px/1.6 system-ui,sans-serif}main{max-width:42rem;margin:12vh auto;padding:2rem}h1{line-height:1.2;font-size:clamp(2rem,6vw,3rem)}a{color:inherit}button{font:inherit;padding:.65rem 1.1rem;border:0;border-radius:.5rem;background:#172c26;color:#fff;cursor:pointer}form{margin:1.5rem 0}</style></head><body><main><h1>${escape(title)}</h1><p>${escape(body)}</p>${form}<a href="/personal">Cuadrao</a></main></body></html>`, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'" },
  });
}
