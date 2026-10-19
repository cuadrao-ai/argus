import { afterEach, describe, expect, test } from "bun:test";
import { resolveRobots } from "next/dist/build/webpack/loaders/metadata/resolve-route-data.js";
import robots from "../app/robots";

const previousIndexing = process.env.CUADRAO_SITE_INDEXING;

afterEach(() => {
  if (previousIndexing === undefined) delete process.env.CUADRAO_SITE_INDEXING;
  else process.env.CUADRAO_SITE_INDEXING = previousIndexing;
});

describe("robots.txt", () => {
  test("a blocked host keeps the global disallow and allows two crawlers on two paths", () => {
    delete process.env.CUADRAO_SITE_INDEXING;

    expect(resolveRobots(robots())).toBe(`User-Agent: facebookexternalhit
Allow: /eliminar-datos
Allow: /privacidad
Disallow: /

User-Agent: Facebot
Allow: /eliminar-datos
Allow: /privacidad
Disallow: /

User-Agent: *
Disallow: /

`);
  });

  test("a public host still allows the site, blocks the API, and names the sitemap", () => {
    process.env.CUADRAO_SITE_INDEXING = "public";

    expect(resolveRobots(robots())).toBe(
      ["User-Agent: *", "Allow: /", "Disallow: /api/", "", "Sitemap: https://cuadrao.ai/sitemap.xml", ""].join("\n"),
    );
  });
});
