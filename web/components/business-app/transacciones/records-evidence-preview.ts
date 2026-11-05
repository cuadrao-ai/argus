import type { ReceiptLimits } from "@/lib/business-api";
import { receiptFileWithType } from "../receipt-file";

export type LocalEvidence = Readonly<{ digest: string; file: File }>;
type FileRejection = "invalid_name" | "unsupported" | "empty_file" | "too_large";
type EvidenceSelection = { kind: "ready"; attachments: readonly LocalEvidence[]; duplicates: number } | { kind: "invalid"; reason: FileRejection; filename: string };

export async function addLocalEvidence(existing: readonly LocalEvidence[], files: readonly File[], limits: ReceiptLimits): Promise<EvidenceSelection> {
  for (const file of files) {
    const filename = typeof file.name === "string" ? file.name : "";
    if (!filename.trim() || filename.length > 255 || filename.includes("/") || filename.includes("\\") || [...filename].some((character) => character.charCodeAt(0) < 32)) return { kind: "invalid", reason: "invalid_name", filename };
  }
  const candidates = files.map((file) => receiptFileWithType(file, limits));
  for (const file of candidates) {
    const reason = !limits.media_types.includes(file.type) ? "unsupported" : file.size === 0 ? "empty_file" : file.size > limits.max_bytes ? "too_large" : null;
    if (reason) return { kind: "invalid", reason, filename: file.name };
  }
  const attachments = [...existing];
  const seen = new Set(existing.map(({ digest }) => digest));
  let duplicates = 0;
  for (const file of candidates) {
    const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    const digest = [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    if (seen.has(digest)) { duplicates++; continue; }
    seen.add(digest);
    attachments.push({ digest, file });
  }
  return { kind: "ready", attachments, duplicates };
}
