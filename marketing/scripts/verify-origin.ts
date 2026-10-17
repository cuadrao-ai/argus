// Read-only acceptance check for a running marketing origin: a Render address,
// the public apex or a local build. It only issues GET requests, so it
// never sends a message, stores a signup or changes anything.
//
//   bun run scripts/verify-origin.ts https://cuadrao-marketing.onrender.com
//   bun run scripts/verify-origin.ts https://cuadrao.ai --public --www https://www.cuadrao.ai
//
// Without --public the origin must be excluded from search. With --public it
// must be indexable and list every page. Expectations come from the route
// owner, so a new page or redirect is checked without editing this file.
import {
  PAGES,
  SITE_ORIGIN,
  SITE_ROUTES,
  alternateLanguages,
  htmlLang,
  nextRedirects,
  type SiteRoute,
} from "../lib/site-routes";

type Result = { check: string; ok: boolean; detail?: string };

const args = process.argv.slice(2);
const origin = (args.find((arg) => /^https?:\/\//.test(arg)) ?? "").replace(/\/$/, "");
const publicHost = args.includes("--public");
const wwwIndex = args.indexOf("--www");
const www = wwwIndex >= 0 ? args[wwwIndex + 1]?.replace(/\/$/, "") : undefined;
if (!origin) {
  console.error("Usage: bun run scripts/verify-origin.ts <origin> [--public] [--www <origin>]");
  process.exit(2);
}
// A redirect must stay on this host. The scheme is not compared: behind Render's TLS
// terminator the app can build an absolute Location with http.
const originHost = new URL(origin).host;

const results: Result[] = [];
function record(check: string, ok: boolean, detail?: string): void {
  results.push({ check, ok, detail: ok ? undefined : detail });
}

async function get(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(origin + path, { redirect: "manual", signal: AbortSignal.timeout(20_000), ...init });
}

function attr(html: string, pattern: RegExp): string | null {
  return html.match(pattern)?.[1] ?? null;
}

async function checkPage(route: SiteRoute): Promise<void> {
  const response = await get(route.path);
  const label = `page ${route.path}`;
  record(`${label} returns 200`, response.status === 200, `got ${response.status}`);
  if (response.status !== 200) return;
  const html = await response.text();
  record(`${label} lang`, html.includes(`<html lang="${htmlLang(route.locale)}"`), "html lang differs");
  record(`${label} title`, /<title>[^<]{8,}<\/title>/.test(html), "missing or short title");
  record(`${label} canonical`, attr(html, /<link rel="canonical" href="([^"]+)"/) === route.url, "canonical differs from the route owner");
  const languages = alternateLanguages(route.page);
  const alternates = [...html.matchAll(/<link rel="alternate" hrefLang="([^"]+)" href="([^"]+)"/g)];
  record(
    `${label} hreflang`,
    alternates.length === 3 && alternates.every(([, lang, href]) => languages[lang] === href),
    `found ${alternates.map(([, lang]) => lang).join(",")}`,
  );
  record(`${label} sets no cookie`, !response.headers.has("set-cookie"), "Set-Cookie present");
  record(`${label} share image`, html.includes(`<meta property="og:image" content="${SITE_ORIGIN}/cuadrao-site/`), "og:image missing or off the public origin");
  const robots = response.headers.get("x-robots-tag");
  record(
    `${label} robots header`,
    publicHost ? robots === null : robots === "noindex, nofollow",
    `x-robots-tag was ${robots}`,
  );
}

async function main(): Promise<void> {
  const health = await get("/api/health");
  record("health 200 json", health.status === 200 && (await health.json()).status === "ok", `got ${health.status}`);

  for (const route of SITE_ROUTES) await checkPage(route);

  for (const redirect of nextRedirects()) {
    const response = await get(redirect.source);
    const location = response.headers.get("location") ?? "";
    const target = new URL(location, origin);
    record(`redirect ${redirect.source}`, response.status === 308 && target.host === originHost && target.pathname === redirect.destination, `got ${response.status} to ${location}`);
  }
  for (const [from, to] of [["/EN", "/en"], ["/en/Personal", "/en/personal"]]) {
    const response = await get(from);
    const target = new URL(response.headers.get("location") ?? "", origin);
    record(`case redirect ${from}`, response.status === 308 && target.host === originHost && target.pathname === to, `got ${response.status}`);
  }
  record("unknown path is 404", (await get("/no-such-page")).status === 404);

  for (const path of ["/icon.svg", "/favicon.ico", "/apple-icon.png"]) {
    const response = await get(path);
    record(`icon ${path}`, response.status === 200 && (response.headers.get("content-type") ?? "").startsWith("image/"), `got ${response.status}`);
  }
  record("no manifest", (await get("/manifest.json")).status === 404);
  record("form endpoints reject GET", (await get("/api/inquiries")).status === 405 && (await get("/api/signups")).status === 405);

  const robotsResponse = await get("/robots.txt");
  const sitemapResponse = await get("/sitemap.xml");
  record("robots.txt returns 200", robotsResponse.status === 200, `got ${robotsResponse.status}`);
  record("sitemap.xml returns 200", sitemapResponse.status === 200, `got ${sitemapResponse.status}`);
  const robots = await robotsResponse.text();
  const sitemap = await sitemapResponse.text();
  // Whole-line matches: "Disallow: /" would otherwise satisfy "Allow: /" and "Disallow: /api/".
  const robotsLine = (line: string) => new RegExp(`^${line.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}$`, "m").test(robots);
  const locations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]).sort();
  if (publicHost) {
    record(
      "robots allows, keeps the API out and names the sitemap",
      robotsLine("Allow: /") && !robotsLine("Disallow: /") && robotsLine("Disallow: /api/") && robotsLine(`Sitemap: ${SITE_ORIGIN}/sitemap.xml`),
      "robots.txt does not match the public expectation",
    );
    record("sitemap lists every page once", JSON.stringify(locations) === JSON.stringify(SITE_ROUTES.map((route) => route.url).sort()), `found ${locations.length}`);
    record("sitemap leaves out private routes", !sitemap.includes("/api/"));
  } else {
    record("robots disallows everything", robotsLine("Disallow: /") && !robotsLine("Allow: /") && !robots.includes("Sitemap"), "robots.txt does not disallow everything");
    record("sitemap is empty", sitemapResponse.status === 200 && locations.length === 0, `status ${sitemapResponse.status}, ${locations.length} urls`);
  }

  if (www) {
    const response = await fetch(www + "/", { redirect: "manual", signal: AbortSignal.timeout(20_000) });
    const location = response.headers.get("location") ?? "";
    record("www redirects to the apex", [301, 302, 307, 308].includes(response.status) && new URL(location, www).origin === origin, `got ${response.status} to ${location}`);
  }
  if (origin.startsWith("https://")) {
    const http = await fetch(origin.replace("https://", "http://") + "/", { redirect: "manual", signal: AbortSignal.timeout(20_000) }).catch(() => null);
    record("plain http upgrades to https", http !== null && [301, 302, 307, 308].includes(http.status) && (http.headers.get("location") ?? "").startsWith("https://"), "http did not redirect to https");
  }

  const failed = results.filter((result) => !result.ok);
  console.log(JSON.stringify({ origin, publicHost, checks: results.length, failed: failed.length, pages: PAGES.length * 2, results }, null, 2));
  process.exit(failed.length ? 1 : 0);
}

await main();
