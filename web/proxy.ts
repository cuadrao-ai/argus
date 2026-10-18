import { NextResponse, type NextRequest } from "next/server";

import { authLinkErrorRedirect } from "./lib/auth-link-error";

export function proxy(request: NextRequest) {
  const { pathname, searchParams, origin } = request.nextUrl;
  if (pathname === "/dev/result-card" || pathname.startsWith("/dev/result-card/")) {
    if (process.env.NODE_ENV === "production") {
      return new NextResponse(null, { status: 404 });
    }
    return NextResponse.next();
  }

  const target = authLinkErrorRedirect({ origin, pathname, searchParams });
  if (target) return NextResponse.redirect(target);
  return NextResponse.next();
}

export const config = {
  matcher: ["/dev/result-card/:path*", "/auth/:path*"],
};
