import { expect, test } from "@playwright/test";
import { PAGE_METADATA, shareImage } from "../lib/page-metadata";
import { SITE_ROUTES, pageUrl } from "../lib/site-routes";
import { PUBLIC_URL } from "./support";

for (const route of SITE_ROUTES) {
  test(`${route.path} serves complete search and link previews without scripts`, async ({ page, request }) => {
    const response = await request.get(`${PUBLIC_URL}${route.path}`, {
      headers: { "user-agent": "WhatsApp/2.26.1", host: "cuadrao.ai" },
    });
    expect(response.status()).toBe(200);
    expect(response.headers()["x-robots-tag"]).toBeUndefined();
    const html = await response.text();
    const tags = await page.evaluate((source) => {
      const document = new DOMParser().parseFromString(source, "text/html");
      const meta = (selector: string) => document.head.querySelector(selector)?.getAttribute("content");
      return {
        title: document.title,
        description: meta('meta[name="description"]'),
        canonical: [...document.head.querySelectorAll('link[rel="canonical"]')].map((link) => link.getAttribute("href")),
        languages: [...document.head.querySelectorAll('link[rel="alternate"][hreflang]')].map((link) => [link.getAttribute("hreflang"), link.getAttribute("href")]),
        robots: [...document.querySelectorAll('meta[name="robots"], meta[name="googlebot"]')].map((tag) => tag.getAttribute("content")),
        og: Object.fromEntries(["title", "description", "url", "site_name", "image", "image:width", "image:height"].map((name) => [name, meta(`meta[property="og:${name}"]`)])),
        social: Object.fromEntries(["card", "title", "description", "image"].map((name) => [name, meta(`meta[name="twitter:${name}"]`)])),
      };
    }, html);
    const copy = PAGE_METADATA[route.locale][route.page]!;
    const image = shareImage(route.locale);
    const imageUrl = new URL(image.url, "https://cuadrao.ai").href;
    expect(tags.title).toBe(copy.title);
    expect(tags.description).toBe(copy.description);
    expect(tags.canonical).toEqual([route.url]);
    expect(tags.languages).toHaveLength(3);
    expect(Object.fromEntries(tags.languages)).toEqual({
      "es": pageUrl("es", route.page), en: pageUrl("en", route.page),
      "x-default": pageUrl("es", route.page),
    });
    expect(tags.robots.join(",")).not.toMatch(/noindex|none/i);
    expect(tags.og).toEqual({
      title: copy.title, description: copy.description, url: route.url, site_name: "Cuadrao",
      image: imageUrl, "image:width": "1200", "image:height": "630",
    });
    expect(tags.social).toEqual({
      card: "summary_large_image", title: copy.title, description: copy.description, image: imageUrl,
    });
    const preview = await request.get(`${PUBLIC_URL}${image.url}`);
    expect(preview.status()).toBe(200);
    expect(preview.headers()["content-type"]).toContain("image/png");
    expect(preview.headers()["x-robots-tag"]).toBeUndefined();
    const png = await preview.body();
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([1200, 630]);

    await page.route("https://cuadrao.ai/**", async (intercept) => {
      const url = new URL(intercept.request().url());
      const local = await intercept.fetch({ url: `${PUBLIC_URL}${url.pathname}${url.search}` });
      await intercept.fulfill({ response: local });
    });
    await page.goto(`https://cuadrao.ai${route.path}`);
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", route.url);
    await expect(page.locator('a[href*="onrender.com"], link[href*="onrender.com"], meta[content*="onrender.com"]')).toHaveCount(0);
  });
}

test("the public sitemap lists exactly the public pages with reciprocal language links", async ({ request, page }) => {
  const response = await request.get(`${PUBLIC_URL}/sitemap.xml`);
  expect(response.status()).toBe(200);
  const entries = await page.evaluate((xml) => {
    const document = new DOMParser().parseFromString(xml, "application/xml");
    return [...document.getElementsByTagName("url")].map((entry) => ({
      url: entry.getElementsByTagName("loc")[0]?.textContent,
      languages: [...entry.getElementsByTagNameNS("http://www.w3.org/1999/xhtml", "link")]
        .map((link) => [link.getAttribute("hreflang"), link.getAttribute("href")]),
    }));
  }, await response.text());
  expect(entries.map((entry) => entry.url).sort()).toEqual(SITE_ROUTES.map((route) => route.url).sort());
  for (const route of SITE_ROUTES) {
    const entry = entries.find((candidate) => candidate.url === route.url)!;
    expect(entry.languages).toHaveLength(3);
    expect(Object.fromEntries(entry.languages)).toEqual({
      "es": pageUrl("es", route.page), en: pageUrl("en", route.page),
      "x-default": pageUrl("es", route.page),
    });
  }
});
