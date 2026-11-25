Bun.serve({
  hostname: "127.0.0.1", port: 3197,
  fetch(request) {
    if (new URL(request.url).pathname === "/health") return new Response("ok");
    const token = request.headers.get("authorization")?.replace("Bearer ", "");
    try {
      const { sub } = JSON.parse(Buffer.from(token.split(".")[1], "base64url"));
      return Response.json({ id: sub, email: `${sub}@example.test`, aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}, created_at: "2026-10-01T00:00:00Z" });
    } catch { return Response.json({ message: "No fixture session" }, { status: 401 }); }
  },
});
