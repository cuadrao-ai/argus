import type { MetadataRoute } from "next";
import { indexingEnabled } from "@/lib/indexing";
import { SITE_ORIGIN } from "@/lib/site-routes";

// Read the environment on every request; a static build would freeze it.
export const dynamic = "force-dynamic";

export default function robots(): MetadataRoute.Robots {
  if (!indexingEnabled(process.env.CUADRAO_SITE_INDEXING)) {
    return { rules: { userAgent: "*", disallow: "/" } };
  }
  return {
    rules: { userAgent: "*", allow: "/", disallow: "/api/" },
    sitemap: `${SITE_ORIGIN}/sitemap.xml`,
  };
}
