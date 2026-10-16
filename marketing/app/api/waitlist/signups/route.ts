import { jsonResponse } from "@/lib/forms/http";

export function POST(): Response {
  return jsonResponse(503, { error: "unavailable" });
}
