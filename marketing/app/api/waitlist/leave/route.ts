import { waitlistResult } from "@/lib/waitlist/result";
import { jsonResponse, logEvent } from "@/lib/forms/http";
import { waitlistDeps } from "@/lib/waitlist/runtime";
import { leaveWaitlist } from "@/lib/waitlist/service";

async function leave(request: Request) {
  const deps = waitlistDeps();
  if (!deps) return jsonResponse(503, { error: "unavailable" });
  try {
    if (!await leaveWaitlist(new URL(request.url).searchParams.get("token") ?? "", deps)) return jsonResponse(400, { error: "invalid" });
    return request.method === "GET" ? waitlistResult("Ya saliste de la lista.", "Borramos tu correo y tus respuestas.") : jsonResponse(200, { status: "removed" });
  } catch {
    logEvent("waitlist_leave_failed");
    return jsonResponse(503, { error: "unavailable" });
  }
}

export const GET = leave;
export const POST = leave;
