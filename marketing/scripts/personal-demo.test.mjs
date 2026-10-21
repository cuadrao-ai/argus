import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { test } from "node:test";
import { createPersonalDemoServer } from "./personal-demo.mjs";

const listen = async (server) => { server.listen(0, "127.0.0.1"); await once(server, "listening"); return `http://127.0.0.1:${server.address().port}`; };

test("local demo simulates signup, blocks mutations and strips credentials", async (t) => {
  const requests = [];
  const upstream = http.createServer((req, res) => {
    requests.push({ method: req.method, url: req.url, headers: req.headers });
    if (req.url === "/redirect") { res.writeHead(307, { Location: `http://127.0.0.1:${upstream.address().port}/en/personal?demo=1` }); res.end(); return; }
    if (req.headers.rsc) { res.setHeader("Content-Type", "text/x-component"); res.end("component-stream"); return; }
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.setHeader("Set-Cookie", "should-not-copy=1");
    res.setHeader("ETag", "old-html");
    res.end("<html><head></head><body>Personal form</body></html>");
  });
  await listen(upstream);
  const demo = createPersonalDemoServer({ upstreamPort: upstream.address().port, delayMs: 1 });
  const origin = await listen(demo);
  t.after(() => { demo.closeAllConnections(); demo.close(); upstream.closeAllConnections(); upstream.close(); });
  const signup = await fetch(`${origin}/api/signups`, { method: "POST", headers: { Origin: origin, "Content-Type": "application/json" }, body: JSON.stringify({ email: "demo@example.test" }) });
  assert.deepEqual(await signup.json(), { status: "registered" });
  assert.equal(signup.headers.get("cache-control"), "no-store");
  assert.equal(requests.length, 0);
  for (const [method, path, requestOrigin] of [["POST", "/api/inquiries", origin], ["DELETE", "/personal", origin], ["GET", "/api/signups", origin], ["POST", "/api/signups", "https://other.example"], ["POST", "/api/signups", null]]) {
    const result = await fetch(origin + path, { method, headers: requestOrigin ? { Origin: requestOrigin } : {} });
    assert.ok([403, 405].includes(result.status));
    await result.text();
  }
  assert.equal(requests.length, 0);
  for (const path of ["/personal?preview=1", "/en/personal"]) {
    const result = await fetch(origin + path, { headers: { Cookie: "session=secret", Authorization: "Bearer secret" } });
    assert.match(await result.text(), /__cuadrao_demo\.js/);
    assert.equal(result.headers.get("etag"), null);
    assert.equal(result.headers.get("set-cookie"), null);
    assert.equal(result.headers.get("x-robots-tag"), "noindex, nofollow");
  }
  assert.equal(requests[0].url, "/personal?preview=1");
  assert.equal(requests[0].headers.cookie, undefined);
  assert.equal(requests[0].headers.authorization, undefined);
  assert.equal(requests[0].headers["accept-encoding"], "identity");
  const rsc = await fetch(`${origin}/en/personal?_rsc=abc`, { headers: { rsc: "1", "next-router-state-tree": "state" } });
  assert.equal(await rsc.text(), "component-stream");
  assert.equal(requests.at(-1).headers["next-router-state-tree"], "state");
  const redirect = await fetch(`${origin}/redirect`, { redirect: "manual" });
  assert.equal(redirect.headers.get("location"), "/en/personal?demo=1");
  const script = await fetch(`${origin}/__cuadrao_demo.js`);
  assert.match(await script.text(), /No emails are saved/);
  const wrongHost = await new Promise((resolve, reject) => {
    http.get(`${origin}/personal`, { headers: { Host: "example.com" } }, (response) => { response.resume(); resolve(response.statusCode); }).on("error", reject);
  });
  assert.equal(wrongHost, 403);
});
