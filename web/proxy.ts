import { NextRequest, NextResponse } from "next/server";

import { decideBusinessOnlyWeb } from "./lib/business-only-web";
import { businessOnlyWebFromEnv } from "./lib/private-alpha-flags";

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (pathname === "/dev/result-card" || pathname.startsWith("/dev/result-card/")) {
    if (process.env.NODE_ENV === "production") {
      return new NextResponse(null, { status: 404 });
    }
    return NextResponse.next();
  }

  const decision = decideBusinessOnlyWeb({
    enabled: businessOnlyWebFromEnv(process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB),
    pathname,
    search,
  });
  if (decision.action === "redirect") {
    return NextResponse.redirect(new URL(decision.location, request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dev/result-card/:path*",
    "/((?!_next/static|_next/image|.*\\..*).*)",
  ],
};
