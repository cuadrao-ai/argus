// Browser-test process only. No production source accepts a verification URL override.
const originalFetch = globalThis.fetch;
globalThis.fetch = (input, init) => {
  if (String(input) === "https://challenges.cloudflare.com/turnstile/v0/siteverify") {
    return Promise.resolve(new Response(JSON.stringify({ success: true, hostname: "cuadrao.example.test", action: "personal_waitlist" }), { headers: { "Content-Type": "application/json" } }));
  }
  return originalFetch(input, init);
};
