export function saveBlobDownload(blob: Blob, filename: string, revokeAfterMs = 30_000) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  // Safari and Firefox read the object URL after click returns; revoke later.
  try { link.click(); } finally { link.remove(); globalThis.setTimeout(() => URL.revokeObjectURL(url), revokeAfterMs); }
}
