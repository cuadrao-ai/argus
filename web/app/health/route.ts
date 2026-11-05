export const dynamic = "force-dynamic";

export function GET(): Response {
  const commit = process.env.RENDER_GIT_COMMIT;
  return Response.json(
    { status: "healthy", git_sha: commit?.length === 40 && /^[0-9a-fA-F]+$/.test(commit) ? commit : null },
    { headers: { "Cache-Control": "no-store" } },
  );
}
