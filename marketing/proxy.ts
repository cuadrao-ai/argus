import { NextRequest, NextResponse } from "next/server";
import { indexingEnabled } from "./lib/indexing";
import { lowercaseRedirectPath } from "./lib/site-routes";

export function proxy(request: NextRequest) {
  // Next matches a route case-insensitively but only prerendered it in
  // lowercase, so one mixed-case request would overwrite the prerender with a
  // 404. Send every spelling to the canonical lowercase path first.
  const canonical = lowercaseRedirectPath(request.nextUrl.pathname);
  if (canonical) {
    const url = request.nextUrl.clone();
    url.pathname = canonical;
    return NextResponse.redirect(url, 308);
  }
  const response = NextResponse.next();
  if (!indexingEnabled(process.env.CUADRAO_SITE_INDEXING)) {
    response.headers.set("X-Robots-Tag", "noindex, nofollow");
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static).*)"],
};
