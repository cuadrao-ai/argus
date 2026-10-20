import { jsonResponse } from "@/lib/forms/http";
import { waitlistDeps } from "@/lib/waitlist/runtime";
import { handleWaitlistSignup } from "@/lib/waitlist/service";

export function POST(request: Request) {
  const deps = waitlistDeps();
  return deps ? handleWaitlistSignup(request, deps) : jsonResponse(503, { error: "unavailable" });
}
