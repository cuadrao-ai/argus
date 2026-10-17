import type { MetadataRoute } from "next";
import { indexingEnabled } from "@/lib/indexing";
import { SITE_ROUTES, alternateLanguages } from "@/lib/site-routes";

export const dynamic = "force-dynamic";

export default function sitemap(): MetadataRoute.Sitemap {
  if (!indexingEnabled(process.env.CUADRAO_SITE_INDEXING)) return [];
  return SITE_ROUTES.map((route) => ({
    url: route.url,
    alternates: { languages: alternateLanguages(route.page) },
  }));
}
