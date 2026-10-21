import { LIMITS } from "./validation";

const NO_STORE = { "Cache-Control": "no-store" } as const;

export function jsonResponse(
  status: number,
  body: Record<string, unknown>,
  headers: Record<string, string> = {},
): Response {
  return Response.json(body, { status, headers: { ...NO_STORE, ...headers } });
}

// Render appends the address it saw to any X-Forwarded-For the client sent, so
// the rightmost entry is the only one the client cannot choose. When a trusted
// proxy such as Cloudflare sits in front, name the header it sets instead.
export function clientKey(request: Request, trustedHeader: string | null = null): string {
  if (trustedHeader) return request.headers.get(trustedHeader)?.trim() || "unknown";
  const forwarded = request.headers.get("x-forwarded-for");
  return forwarded?.split(",").at(-1)?.trim() || "unknown";
}

// The page posts from its own origin. A browser at another origin could only
// reach this route with a request the browser itself refuses to expose.
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    return new URL(origin).host === request.headers.get("host");
  } catch {
    return false;
  }
}

export type BodyResult =
  | { ok: true; body: unknown }
  | { ok: false; status: 400 | 413 | 415 };

export async function readJsonBody(request: Request): Promise<BodyResult> {
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return { ok: false, status: 415 };
  }
  const declared = Number(request.headers.get("content-length") ?? 0);
  if (declared > LIMITS.bodyBytes) return { ok: false, status: 413 };
  const reader = request.body?.getReader();
  if (!reader) return { ok: false, status: 400 };
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > LIMITS.bodyBytes) {
      await reader.cancel();
      return { ok: false, status: 413 };
    }
    chunks.push(value);
  }
  try {
    return { ok: true, body: JSON.parse(Buffer.concat(chunks).toString("utf8")) };
  } catch {
    return { ok: false, status: 400 };
  }
}

// Visitor text and addresses never reach logs; only the event and its outcome.
export function logEvent(event: string, fields: Record<string, string | number> = {}): void {
  console.log(JSON.stringify({ event, ...fields }));
}
