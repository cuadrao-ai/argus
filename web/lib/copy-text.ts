/**
 * Copy text to the device clipboard without ever throwing: the async
 * clipboard first, a selected hidden textarea as the fallback, and false
 * when neither works (an insecure context, a denied permission, no DOM).
 */
export async function copyText(
  text: string,
  clipboard: Pick<Clipboard, "writeText"> | null | undefined = typeof navigator === "undefined" ? null : navigator.clipboard,
  doc: Document | null | undefined = typeof document === "undefined" ? null : document,
): Promise<boolean> {
  if (clipboard) {
    try {
      await clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to the selection fallback.
    }
  }
  if (!doc?.body) return false;
  try {
    const area = doc.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    doc.body.appendChild(area);
    area.select();
    const copied = doc.execCommand("copy");
    doc.body.removeChild(area);
    return copied;
  } catch {
    return false;
  }
}
