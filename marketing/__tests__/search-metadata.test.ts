import { afterEach, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { generateMetadata, generateStaticParams } from "../app/[locale]/[[...slug]]/page";
import sitemap from "../app/sitemap";
import { SITE_ORIGIN, SITE_ROUTES, pageUrl, slugSegments } from "../lib/site-routes";
import { shareImage } from "../lib/page-metadata";

const previousIndexing = process.env.CUADRAO_SITE_INDEXING;

afterEach(() => {
  if (previousIndexing === undefined) delete process.env.CUADRAO_SITE_INDEXING;
  else process.env.CUADRAO_SITE_INDEXING = previousIndexing;
});

for (const route of SITE_ROUTES) {
  test(`${route.path} has a canonical and reciprocal language alternatives`, async () => {
    const metadata = await generateMetadata({
      params: Promise.resolve({ locale: route.locale, slug: slugSegments(route.locale, route.page) }),
    });
    expect(metadata.metadataBase?.href).toBe(`${SITE_ORIGIN}/`);
    expect(metadata.alternates?.canonical).toBeTruthy();
    expect(new URL(String(metadata.alternates?.canonical), metadata.metadataBase!).href)
      .toBe(new URL(route.url).href);
    expect(metadata.alternates?.languages).toEqual({
      "es": pageUrl("es", route.page),
      en: pageUrl("en", route.page),
      "x-default": pageUrl("es", route.page),
    });
    expect(metadata.robots).toBeUndefined();
  });
}

test("every public page has distinct populated search and social copy", async () => {
  const titles = new Set<string>();
  const descriptions = new Set<string>();
  for (const route of SITE_ROUTES) {
    const metadata = await generateMetadata({
      params: Promise.resolve({ locale: route.locale, slug: slugSegments(route.locale, route.page) }),
    });
    expect(metadata.title).toHaveProperty("absolute");
    const title = (metadata.title as { absolute: string }).absolute;
    expect(title.trim().length).toBeGreaterThan(0);
    expect(metadata.description?.trim().length).toBeGreaterThan(0);
    titles.add(title);
    descriptions.add(metadata.description!);
    expect(metadata.openGraph).toMatchObject({
      title, description: metadata.description, siteName: "Cuadrao",
      images: [shareImage(route.locale)],
    });
    expect(metadata.twitter).toMatchObject({
      card: "summary_large_image", title, description: metadata.description,
      images: [shareImage(route.locale).url],
    });
  }
  expect(titles.size).toBe(SITE_ROUTES.length);
  expect(descriptions.size).toBe(SITE_ROUTES.length);
});

test("preview PNG dimensions match the declared 1200 by 630 pixels", () => {
  for (const locale of ["es", "en"] as const) {
    const image = shareImage(locale);
    const bytes = readFileSync(new URL(`../public${image.url}`, import.meta.url));
    expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    expect([bytes.readUInt32BE(16), bytes.readUInt32BE(20)]).toEqual([1200, 630]);
    expect([image.width, image.height]).toEqual([1200, 630]);
  }
});

test("public sitemap and generated pages match the public route list exactly", () => {
  process.env.CUADRAO_SITE_INDEXING = "public";
  const entries = sitemap();
  expect(entries.map((entry) => entry.url).sort()).toEqual(SITE_ROUTES.map((route) => route.url).sort());
  expect(new Set(entries.map((entry) => entry.url)).size).toBe(entries.length);
  expect(generateStaticParams()).toEqual(SITE_ROUTES.map((route) => ({
    locale: route.locale, slug: slugSegments(route.locale, route.page),
  })));
  for (const route of SITE_ROUTES) {
    expect(entries.find((entry) => entry.url === route.url)?.alternates?.languages).toEqual({
      "es": pageUrl("es", route.page),
      en: pageUrl("en", route.page),
      "x-default": pageUrl("es", route.page),
    });
    expect(new URL(route.url).origin).toBe("https://cuadrao.ai");
    expect(new URL(route.url).pathname).not.toMatch(/^\/(api|es|private|preview)(\/|$)/);
  }
});

test("the sitemap stays empty unless indexing is explicitly public", () => {
  delete process.env.CUADRAO_SITE_INDEXING;
  expect(sitemap()).toEqual([]);
  for (const value of ["", "private", "PUBLIC", "true"]) {
    process.env.CUADRAO_SITE_INDEXING = value;
    expect(sitemap()).toEqual([]);
  }
});
