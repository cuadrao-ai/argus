import type { MetadataRoute } from "next";
import { indexingEnabled, PRIVATE_HOST_INDEXABLE_PATHS } from "@/lib/indexing";
import { SITE_ORIGIN } from "@/lib/site-routes";

// Read the environment on every request; a static build would freeze it.
export const dynamic = "force-dynamic";

const crawlerAllow = [...PRIVATE_HOST_INDEXABLE_PATHS];

export default function robots(): MetadataRoute.Robots {
  if (!indexingEnabled(process.env.CUADRAO_SITE_INDEXING)) {
    return {
      rules: [
        { userAgent: "facebookexternalhit", allow: crawlerAllow, disallow: "/" },
        { userAgent: "Facebot", allow: crawlerAllow, disallow: "/" },
        { userAgent: "*", disallow: "/" },
      ],
    };
  }
  return {
    rules: { userAgent: "*", allow: "/", disallow: "/api/" },
    sitemap: `${SITE_ORIGIN}/sitemap.xml`,
  };
}
