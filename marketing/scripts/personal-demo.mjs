import http from "node:http";
import { pathToFileURL } from "node:url";

const assetPrefix = "/__cuadrao_demo";
const demoScript = `window.addEventListener("load", () => {
  const badge = document.createElement("aside");
  badge.id = "cuadrao-local-demo";
  badge.setAttribute("aria-label", "Demo local / Local demo");
  const label = document.createElement("span");
  label.textContent = "Demo · No se guardan correos / No emails are saved";
  const replay = document.createElement("a");
  replay.href = location.pathname;
  replay.textContent = "Repetir / Replay ↻";
  replay.addEventListener("click", (event) => { event.preventDefault(); location.reload(); });
  badge.append(label, replay);
  document.body.append(badge);
});`;
const demoStyle = `#cuadrao-local-demo{position:fixed;z-index:100;bottom:16px;left:16px;right:auto;display:flex;align-items:center;gap:20px;max-width:calc(100vw - 32px);box-sizing:border-box;padding:12px 16px;border:1px solid #456750;border-radius:14px;background:#f2f8e8;color:#183629;box-shadow:0 4px 20px #18362920;font:13px/1.4 system-ui,sans-serif}#cuadrao-local-demo a{color:inherit;font-weight:650;white-space:nowrap}#cuadrao-local-demo a:focus-visible{outline:2px solid #183629;outline-offset:4px}@media(max-width:420px){#cuadrao-local-demo{gap:12px;font-size:11px;padding:10px 12px}}`;
const forwardHeaders = ["accept", "accept-language", "range", "if-none-match", "rsc", "next-router-state-tree", "next-router-prefetch", "next-url"];

export function createPersonalDemoServer({ upstreamPort = 4512, delayMs = 650 } = {}) {
  if (!Number.isInteger(upstreamPort) || upstreamPort < 1 || upstreamPort > 65535) throw new Error("Invalid loopback upstream port");
  const server = http.createServer((request, response) => {
    const origin = `http://127.0.0.1:${server.address().port}`;
    const reply = (status, body, contentType = "text/plain; charset=utf-8") => {
      response.writeHead(status, { "Content-Type": contentType, "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "X-Cuadrao-Demo": "local-only" });
      response.end(request.method === "HEAD" ? undefined : body);
    };
    if (request.headers.host !== new URL(origin).host || (request.headers.origin && request.headers.origin !== origin) || request.headers["sec-fetch-site"] === "cross-site") {
      request.resume();
      reply(403, "This demo is local and same-origin only.");
      return;
    }
    const url = new URL(request.url, origin);
    if (url.origin !== origin) {
      request.resume();
      reply(403, "External destinations are not supported.");
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/signups") {
      if (request.headers.origin !== origin) {
        request.resume();
        reply(403, "A same-origin browser submission is required.");
        return;
      }
      request.resume();
      request.on("end", () => {
        const timer = setTimeout(() => reply(200, JSON.stringify({ status: "registered" }), "application/json"), delayMs);
        response.on("close", () => clearTimeout(timer));
      });
      return;
    }
    if (!["GET", "HEAD"].includes(request.method) || url.pathname.startsWith("/api/")) {
      request.resume();
      reply(405, "Only the simulated signup is available in this demo.");
      return;
    }
    if (url.pathname === `${assetPrefix}.js`) { reply(200, demoScript, "text/javascript; charset=utf-8"); return; }
    if (url.pathname === `${assetPrefix}.css`) { reply(200, demoStyle, "text/css; charset=utf-8"); return; }
    if (url.pathname === "/") { response.writeHead(302, { Location: "/personal", "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow" }); response.end(); return; }
    const headers = Object.fromEntries(forwardHeaders.filter((name) => request.headers[name] !== undefined).map((name) => [name, request.headers[name]]));
    headers["accept-encoding"] = "identity";
    const upstream = http.request({ hostname: "127.0.0.1", port: upstreamPort, path: url.pathname + url.search, method: request.method, headers }, (incoming) => {
      const outputHeaders = { ...incoming.headers, "cache-control": "no-store", "x-robots-tag": "noindex, nofollow", "x-cuadrao-demo": "local-only" };
      delete outputHeaders["set-cookie"];
      if (outputHeaders.location) {
        const destination = new URL(outputHeaders.location, `http://127.0.0.1:${upstreamPort}`);
        if (destination.origin === `http://127.0.0.1:${upstreamPort}`) outputHeaders.location = destination.pathname + destination.search + destination.hash;
      }
      const personalHtml = /^\/(en\/)?personal\/?$/.test(url.pathname) && incoming.headers["content-type"]?.includes("text/html") && request.method !== "HEAD";
      if (!personalHtml) { response.writeHead(incoming.statusCode ?? 502, outputHeaders); incoming.pipe(response); return; }
      delete outputHeaders["content-length"];
      delete outputHeaders["content-encoding"];
      delete outputHeaders.etag;
      const chunks = [];
      incoming.on("data", (chunk) => chunks.push(chunk));
      incoming.on("end", () => {
        const html = Buffer.concat(chunks).toString("utf8")
          .replace("</head>", `<link rel="stylesheet" href="${assetPrefix}.css"></head>`)
          .replace("</body>", `<script src="${assetPrefix}.js" defer></script></body>`);
        response.writeHead(incoming.statusCode ?? 502, outputHeaders);
        response.end(html);
      });
    });
    upstream.on("error", () => { if (!response.headersSent) reply(502, "Start the Marketing preview on 127.0.0.1:4512 first."); else response.destroy(); });
    response.on("close", () => upstream.destroy());
    upstream.end();
  });
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  createPersonalDemoServer().listen(4513, "127.0.0.1", () => {
    console.log("Local animation demo http://127.0.0.1:4513/personal. Signups are simulated. No emails are saved or sent.");
  });
}
