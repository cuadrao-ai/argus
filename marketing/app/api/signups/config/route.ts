export function GET(): Response {
  return Response.json({ siteKey: process.env.CUADRAO_WAITLIST_TURNSTILE_SITE_KEY?.trim() || null }, {
    headers: { "Cache-Control": "no-store" },
  });
}
