import { jsonResponse, logEvent } from "@/lib/forms/http";
import { waitlistDeps } from "@/lib/waitlist/runtime";
import { confirmWaitlist } from "@/lib/waitlist/service";
import { waitlistResult } from "@/lib/waitlist/result";

export async function GET(request: Request) {
  const deps = waitlistDeps();
  if (!deps) return jsonResponse(503, { error: "unavailable" });
  try {
    if (!await confirmWaitlist(new URL(request.url).searchParams.get("token") ?? "", deps)) return waitlistResult("Este enlace ya no está disponible.", "Vuelve a anotarte para recibir otro enlace.", 400);
    return waitlistResult("Ya estás en la lista.", "Gracias por anotarte en la lista de la app personal de Cuadrao. Estamos construyendo Cuadrao para ti y te escribiremos cuando esté listo.");
  } catch {
    logEvent("waitlist_confirmation_failed");
    return jsonResponse(503, { error: "unavailable" });
  }
}
