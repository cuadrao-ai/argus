// Capture the exact request used by ReceiptIntakeDialog's upload queue.
// Only authentication and the network are replaced; the request producer runs.
import { mock } from "bun:test";

const input = await Bun.stdin.json();
mock.module("../../lib/chat-auth-ownership", () => ({
  authenticatedRequestHeaders: async () => ({ Authorization: `Bearer ${input.token}` }),
}));
const { uploadBusinessReceipt } = await import("../../lib/business-api");
let captured: { path: string; method: string; headers: Record<string, string>; content: string } | undefined;
globalThis.fetch = async (url, options) => {
  const request = new Request(url, options);
  captured = {
    path: new URL(request.url).pathname,
    method: request.method,
    headers: Object.fromEntries(request.headers.entries()),
    content: Buffer.from(await request.arrayBuffer()).toString("base64"),
  };
  return Response.json({});
};
await uploadBusinessReceipt(
  new File([Buffer.from(input.content, "base64")], input.filename, { type: input.media_type }),
  input.consent,
  input.key,
);
if (!captured) throw new Error("The modal did not produce an upload request");
process.stdout.write(JSON.stringify(captured));
