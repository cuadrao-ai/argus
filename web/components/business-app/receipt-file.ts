import type { ReceiptLimits } from "@/lib/business-api";

/** Labels and extensions for the server's accepted media types; unknown types show as is. */
const FILE_TYPES: Record<string, { label: string; extensions: string[] }> = {
  "application/pdf": { label: "PDF", extensions: ["pdf"] },
  "image/jpeg": { label: "JPG", extensions: ["jpg", "jpeg"] },
  "image/png": { label: "PNG", extensions: ["png"] },
  "text/plain": { label: "TXT", extensions: ["txt"] },
  "text/csv": { label: "CSV", extensions: ["csv"] },
  "message/rfc822": { label: "EML", extensions: ["eml"] },
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": { label: "XLSX", extensions: ["xlsx"] },
  "application/xml": { label: "XML", extensions: ["xml"] },
  "text/xml": { label: "XML", extensions: ["xml"] },
};

export function receiptFormatLabel(type: string): string {
  return FILE_TYPES[type]?.label ?? type;
}

export function receiptFormatLabels(limits: ReceiptLimits): string[] {
  return [...new Set(limits.media_types.map(receiptFormatLabel))];
}

export function receiptFileAccept(limits: ReceiptLimits): string {
  return [...new Set(limits.media_types.flatMap((type) => [type, ...(FILE_TYPES[type]?.extensions ?? []).map((extension) => `.${extension}`)]))].join(",");
}

/** Browsers leave some files untyped (CSV, EML); the extension names the type when the server accepts it. */
export function receiptFileWithType(file: File, limits: ReceiptLimits): File {
  if (file.type) return file;
  const extension = file.name.split(".").pop()?.toLowerCase();
  const type = limits.media_types.find((media) => FILE_TYPES[media]?.extensions.includes(extension ?? ""));
  return type ? new File([file], file.name, { type, lastModified: file.lastModified }) : file;
}
