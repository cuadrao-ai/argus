import type { BusinessSetup } from "@/lib/business-setup-api";

/** The local design preview's `GET /business/setup` answers, in the server's shape. `?setup=new` is a brand-new Business. */
export const SETUP_FIXTURES: Record<"active" | "new", BusinessSetup> = {
  active: {
    steps: [
      { key: "created", required: true, done: true },
      { key: "fiscal_identity", required: true, done: false },
      { key: "receiving_address", required: true, done: true },
      { key: "receipt_reading", required: true, done: false },
      { key: "first_document", required: false, done: false },
      { key: "team", required: false, done: false },
      { key: "whatsapp", required: false, done: false },
    ],
  },
  new: {
    steps: [
      { key: "created", required: true, done: true },
      { key: "fiscal_identity", required: true, done: false },
      { key: "receiving_address", required: true, done: false },
      { key: "receipt_reading", required: true, done: false },
      { key: "first_document", required: false, done: false },
      { key: "team", required: false, done: false },
      { key: "whatsapp", required: false, done: false },
    ],
  },
};

/** Which fixture the preview answers with: `?setup=new` in the local design preview, else the established sample. */
export function sampleSetup(): BusinessSetup {
  const stage = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("setup") === "new" ? "new" : "active";
  return structuredClone(SETUP_FIXTURES[stage]);
}
