import { waitlistResult } from "@/lib/waitlist/result";
import { jsonResponse, logEvent } from "@/lib/forms/http";
import { waitlistDeps } from "@/lib/waitlist/runtime";
import { leaveWaitlist } from "@/lib/waitlist/service";

export function GET(request: Request) {
  const url = new URL(request.url);
  const action = `/api/waitlist/leave?${new URLSearchParams({ token: url.searchParams.get("token") ?? "" })}`;
  return waitlistResult("Salir de la lista", "", 200, { url: action, label: "Salir de la lista" });
}

export async function POST(request: Request) {
  const deps = waitlistDeps();
  if (!deps) return jsonResponse(503, { error: "unavailable" });
  try {
    if (!await leaveWaitlist(new URL(request.url).searchParams.get("token") ?? "", deps)) return jsonResponse(400, { error: "invalid" });
    return request.headers.get("accept")?.includes("text/html")
      ? waitlistResult("Ya saliste de la lista.", "Borramos tu correo y tus respuestas.")
      : jsonResponse(200, { status: "removed" });
  } catch {
    logEvent("waitlist_leave_failed");
    return jsonResponse(503, { error: "unavailable" });
  }
}
