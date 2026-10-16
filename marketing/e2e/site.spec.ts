import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { PUBLIC_URL, asNewClient } from "./support";

const PAGES = [
  { path: "/", lang: "es-DO", title: "Cada cuenta. En su sitio. | Cuadrao", canonical: "https://cuadrao.ai", alternate: "https://cuadrao.ai/en" },
  { path: "/personal", lang: "es-DO", title: "Tus finanzas, en orden. | Cuadrao Personal", canonical: "https://cuadrao.ai/personal", alternate: "https://cuadrao.ai/en/personal" },
  { path: "/contacto", lang: "es-DO", title: "Hablemos de tu negocio | Cuadrao", canonical: "https://cuadrao.ai/contacto", alternate: "https://cuadrao.ai/en/contact" },
  { path: "/privacidad", lang: "es-DO", title: "Privacidad | Cuadrao", canonical: "https://cuadrao.ai/privacidad", alternate: "https://cuadrao.ai/en/privacy" },
  { path: "/en", lang: "en", title: "Every record. In its place. | Cuadrao", canonical: "https://cuadrao.ai/en", alternate: "https://cuadrao.ai" },
  { path: "/en/personal", lang: "en", title: "Your finances, in order. | Cuadrao Personal", canonical: "https://cuadrao.ai/en/personal", alternate: "https://cuadrao.ai/personal" },
  { path: "/en/contact", lang: "en", title: "Let's talk about your business | Cuadrao", canonical: "https://cuadrao.ai/en/contact", alternate: "https://cuadrao.ai/contacto" },
  { path: "/en/privacy", lang: "en", title: "Privacy | Cuadrao", canonical: "https://cuadrao.ai/en/privacy", alternate: "https://cuadrao.ai/privacidad" },
];

test.beforeEach(async ({ context }, info) => {
  await asNewClient(context, info);
});

test.describe("page identity", () => {
  for (const entry of PAGES) {
    test(`${entry.path} declares its language, title, canonical and alternates`, async ({ page }) => {
      await page.goto(entry.path);
      await expect(page.locator("html")).toHaveAttribute("lang", entry.lang);
      await expect(page).toHaveTitle(entry.title);
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", entry.canonical);
      const languages = await page.locator('link[rel="alternate"][hreflang]').evaluateAll((links) =>
        links.map((link) => [link.getAttribute("hreflang"), link.getAttribute("href")]),
      );
      expect(languages).toContainEqual([entry.lang.startsWith("es") ? "en" : "es", entry.alternate]);
      expect(languages.map(([lang]) => lang).sort()).toEqual(["en", "es", "x-default"]);
      await expect(page.locator('meta[property="og:image"]')).toHaveAttribute("content", /^https:\/\/cuadrao\.ai\/cuadrao-site\/share-(business|personal)-(es|en)\.png$/);
      await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /.{40,}/);
      await expect(page.locator('link[rel="manifest"]')).toHaveCount(0);
    });
  }

  test("every page serves the Cuadrao icons, not an inherited Argus icon", async ({ page, request }) => {
    await page.goto("/");
    const icons = await page.locator('link[rel~="icon"], link[rel="apple-touch-icon"]').evaluateAll((links) =>
      links.map((link) => link.getAttribute("href")),
    );
    expect(icons.length).toBeGreaterThanOrEqual(2);
    for (const href of [...icons, "/favicon.ico"]) {
      const response = await request.get(href!);
      expect(response.status(), href!).toBe(200);
      expect(response.headers()["content-type"], href!).toMatch(/image\//);
    }
    const svg = await (await request.get("/icon.svg")).text();
    expect(svg).toContain('fill="#fafbf8"');
    expect(svg).toContain('stop-color="#2f5a49"');
    expect(svg).toContain("skewX(-12)");
    expect((await request.get("/manifest.json")).status()).toBe(404);
  });

  test("language links keep the visitor on the same page", async ({ page }) => {
    // Below the desktop width the links live in the menu.
    const open = async () => {
      const menu = page.getByRole("button", { name: /Abrir menú|Open menu/ });
      if (await menu.isVisible()) await menu.click();
    };
    await page.goto("/contacto");
    await open();
    await page.locator('header a[hreflang="en"]:visible').first().click();
    await expect(page).toHaveURL(/\/en\/contact$/);
    await open();
    await page.locator('header a[hreflang="es"]:visible').first().click();
    await expect(page).toHaveURL(/\/contacto$/);
  });
});

test.describe("routes", () => {
  for (const [from, to] of [
    ["/business", "/"],
    ["/business/personal", "/personal"],
    ["/business/demo", "/contacto"],
    ["/business/en", "/en"],
    ["/business/en/personal", "/en/personal"],
    ["/business/en/demo", "/en/contact"],
    ["/es", "/"],
    ["/es/contacto", "/contacto"],
  ]) {
    test(`${from} redirects permanently to ${to}`, async ({ request }) => {
      const response = await request.get(from, { maxRedirects: 0 });
      expect(response.status()).toBe(308);
      expect(new URL(response.headers().location, "http://localhost").pathname).toBe(to);
    });
  }

  for (const path of ["/foo", "/en/foo", "/contact", "/en/contacto", "/api/inquiries/x", "/business/private"]) {
    test(`${path} is not found`, async ({ request }) => {
      expect((await request.get(path)).status()).toBe(404);
    });
  }

  test("the not-found page has a language, a title and a way home in both languages", async ({ page }) => {
    const response = await page.goto("/no-such-page");
    expect(response?.status()).toBe(404);
    await expect(page.locator("html")).toHaveAttribute("lang", "es-DO");
    await expect(page).toHaveTitle(/Cuadrao/);
    await expect(page.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/");
    await expect(page.getByRole("link", { name: "Go to the home page" })).toHaveAttribute("href", "/en");
  });

  for (const [from, to] of [["/EN", "/en"], ["/en/Personal", "/en/personal"], ["/En/PRIVACY", "/en/privacy"], ["/Contacto", "/contacto"]]) {
    test(`${from} redirects to ${to} and does not poison the lowercase page`, async ({ request }) => {
      const response = await request.get(`${from}?x=1`, { maxRedirects: 0 });
      expect(response.status()).toBe(308);
      expect(response.headers().location).toMatch(new RegExp(`${to}\\?x=1$`));
      expect((await request.get(to)).status()).toBe(200);
    });
  }

  test("the health endpoint needs no providers", async ({ request }) => {
    const response = await request.get("/api/health");
    expect(response.status()).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
  });

  test("images on a candidate host are also excluded from search", async ({ request }) => {
    const response = await request.get("/_next/image?url=%2Fcuadrao-site%2Fpersonal-home-preview.png&w=640&q=75");
    expect(response.status()).toBe(200);
    expect(response.headers()["x-robots-tag"]).toBe("noindex, nofollow");
  });

  test("form endpoints reject GET", async ({ request }) => {
    expect((await request.get("/api/inquiries")).status()).toBe(405);
    expect((await request.get("/api/signups")).status()).toBe(405);
  });
});

test.describe("indexing", () => {
  test("a candidate host is excluded from search", async ({ request }) => {
    const robots = await (await request.get("/robots.txt")).text();
    expect(robots).toContain("Disallow: /");
    expect(robots).not.toContain("Sitemap");
    const page = await request.get("/");
    expect(page.headers()["x-robots-tag"]).toBe("noindex, nofollow");
    expect(await (await request.get("/sitemap.xml")).text()).not.toContain("<loc>");
  });

  test("the public host is indexable and lists every page once, without private routes", async ({ request }) => {
    const robots = await (await request.get(`${PUBLIC_URL}/robots.txt`)).text();
    expect(robots).toContain("Allow: /");
    expect(robots).toContain("Disallow: /api/");
    expect(robots).toContain("Sitemap: https://cuadrao.ai/sitemap.xml");
    expect((await request.get(`${PUBLIC_URL}/`)).headers()["x-robots-tag"]).toBeUndefined();
    const sitemap = await (await request.get(`${PUBLIC_URL}/sitemap.xml`)).text();
    const locations = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
    expect(locations.sort()).toEqual([...PAGES.map((entry) => entry.canonical), "https://cuadrao.ai/terminos", "https://cuadrao.ai/eliminar-datos"].sort());
    expect(sitemap).not.toContain("/api/");
    expect(sitemap).toContain('hreflang="en"');
  });
});

test.describe("accessibility", () => {
  for (const entry of PAGES) {
    test(`${entry.path} has no automated WCAG 2.1 AA violations`, async ({ page }) => {
      // Entrance animations pass through low-contrast frames that are not the resting state.
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto(entry.path);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(results.violations.map((violation) => `${violation.id}: ${violation.nodes.length} nodes`)).toEqual([]);
    });
  }
});
