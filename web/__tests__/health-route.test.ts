import { afterEach, expect, test } from "bun:test";
import { GET, dynamic } from "@/app/health/route";

const original = process.env.RENDER_GIT_COMMIT;
afterEach(() => {
  if (original === undefined) delete process.env.RENDER_GIT_COMMIT;
  else process.env.RENDER_GIT_COMMIT = original;
});

test.each(["a".repeat(40), "B".repeat(40), undefined, "", "abc123", "invalid".repeat(8)])("health reports deployment metadata %s", async (commit) => {
  if (commit === undefined) delete process.env.RENDER_GIT_COMMIT;
  else process.env.RENDER_GIT_COMMIT = commit;
  const response = GET();
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ status: "healthy", git_sha: commit === "a".repeat(40) || commit === "B".repeat(40) ? commit : null });
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(dynamic).toBe("force-dynamic");
});
