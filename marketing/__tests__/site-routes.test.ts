import { describe, expect, test } from "bun:test";
import {
  LOCALES,
  PAGES,
  pagesForLocale,
  SITE_ORIGIN,
  SITE_ROUTES,
  alternateLanguages,
  businessPath,
  internalPath,
  lowercaseRedirectPath,
  nextRedirects,
  nextRewrites,
  pageUrl,
  pageFromSlug,
  slugSegments,
} from "../lib/site-routes";

describe("public URL map", () => {
  test("Spanish is unprefixed and English lives under /en", () => {
    expect(SITE_ROUTES.map((route) => route.path)).toEqual([
      "/",
      "/personal",
      "/contacto",
      "/privacidad",
      "/terminos",
      "/eliminar-datos",
      "/en",
      "/en/personal",
      "/en/contact",
      "/en/privacy",
    ]);
  });

  test("every route is canonical on the public origin", () => {
    for (const route of SITE_ROUTES) {
      expect(route.url).toBe(`${SITE_ORIGIN}${route.path === "/" ? "" : route.path}`);
    }
  });

  test.each(LOCALES)("slugs resolve back to their page in %s", (locale) => {
    for (const page of pagesForLocale(locale)) {
      expect(pageFromSlug(locale, slugSegments(locale, page))).toBe(page);
    }
  });

  test.each([["private"], ["demo"], ["personal", "extra"], ["es"]])(
    "does not claim an unknown slug %p",
    (...slug) => {
      expect(pageFromSlug("es", slug)).toBeNull();
    },
  );

  test("the English contact slug is not a Spanish page", () => {
    expect(pageFromSlug("es", ["contact"])).toBeNull();
    expect(pageFromSlug("en", ["contacto"])).toBeNull();
  });
});

describe("case handling", () => {
  test.each([
    ["/EN", "/en"],
    ["/en/Personal", "/en/personal"],
    ["/En/PRIVACY", "/en/privacy"],
    ["/Contacto", "/contacto"],
  ])("%s redirects to %s", (path, expected) => {
    expect(lowercaseRedirectPath(path)).toBe(expected);
  });

  test("an already lowercase path is left alone", () => {
    for (const route of SITE_ROUTES) expect(lowercaseRedirectPath(route.path)).toBeNull();
  });
});

describe("alternates", () => {
  test.each(PAGES)("%s links both languages and defaults to Spanish", (page) => {
    const alternates = alternateLanguages(page);
    expect(alternates.es).toBe(pageUrl("es", page));
    if (page === "terms" || page === "deletion") expect(alternates.en).toBeUndefined();
    else expect(alternates.en).toBe(pageUrl("en", page));
    expect(alternates["x-default"]).toBe(alternates.es);
  });
});

describe("redirects and rewrites", () => {
  const redirects = nextRedirects();
  const rewrites = nextRewrites();

  test.each([
    ["/business", "/"],
    ["/business/personal", "/personal"],
    ["/business/demo", "/contacto"],
    ["/business/en", "/en"],
    ["/business/en/personal", "/en/personal"],
    ["/business/en/demo", "/en/contact"],
  ])("old marketing path %s permanently redirects to %s", (source, destination) => {
    expect(redirects).toContainEqual({ source, destination, permanent: true });
  });

  test("the internal Spanish tree is never public", () => {
    for (const page of PAGES) {
      expect(redirects).toContainEqual({
        source: internalPath("es", page),
        destination: businessPath("es", page),
        permanent: true,
      });
    }
  });

  test("every Spanish public path rewrites to the internal tree", () => {
    expect(rewrites).toContainEqual({ source: "/", destination: "/es" });
    expect(rewrites).toContainEqual({ source: "/contacto", destination: "/es/contacto" });
    expect(rewrites).toHaveLength(PAGES.length);
  });

  test("no redirect source is also a public route", () => {
    const publicPaths = new Set(SITE_ROUTES.map((route) => route.path));
    for (const redirect of redirects) expect(publicPaths.has(redirect.source)).toBe(false);
  });
});
