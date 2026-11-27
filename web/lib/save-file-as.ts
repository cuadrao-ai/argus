import { saveBlobDownload } from "./save-blob-download";

export type SaveAsFormat = "xlsx" | "csv";

type Writable = { write(data: Blob): Promise<void>; close(): Promise<void>; abort(): Promise<void> };
type FileHandle = { createWritable(): Promise<Writable>; getFile?(): Promise<Blob>; remove?(): Promise<void> };
type SaveFilePicker = (options: { suggestedName: string; id: string; types: { description?: string; accept: Record<string, string[]> }[] }) => Promise<FileHandle>;

/** One picker id per type, so the system window remembers a folder for Excel and another for CSV. */
const TYPES: Record<SaveAsFormat, { id: string; accept: Record<string, string[]> }> = {
  xlsx: { id: "cuadrao-export-xlsx", accept: { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] } },
  csv: { id: "cuadrao-export-csv", accept: { "text/csv": [".csv"] } },
};

/** A place the person chose in the system Save As window, for the file named `filename`. */
export type SaveAsPlace = {
  filename: string;
  write(blob: Blob): Promise<void>;
  /** Removes the file the window made on the pick, only while it is still empty and no write landed in it. */
  discard(): Promise<void>;
};

function crossOriginFrame(): boolean {
  try { return window.top !== window.self && window.top?.location.origin !== window.location.origin; } catch { return true; }
}

/** The system Save As window, when this browser has one here: a feature check, never the browser's name. */
function saveFilePicker(): SaveFilePicker | null {
  if (typeof window === "undefined") return null;
  const picker = (window as { showSaveFilePicker?: SaveFilePicker }).showSaveFilePicker;
  return typeof picker === "function" && !crossOriginFrame() ? picker.bind(window) : null;
}

export function canSaveAs(): boolean {
  return saveFilePicker() !== null;
}

/**
 * Opens the Save As window with the server's file name. Call it first in the
 * click, before any await: the browser opens it only during the click.
 * `cancelled` when the person closes it; null when there is no window here or
 * it fails, and the file then downloads as before.
 */
export async function chooseSavePlace(filename: string, format: SaveAsFormat): Promise<SaveAsPlace | "cancelled" | null> {
  const picker = saveFilePicker();
  if (!picker) return null;
  let handle: FileHandle;
  try {
    handle = await picker({ suggestedName: filename, id: TYPES[format].id, types: [{ accept: TYPES[format].accept }] });
  } catch (error) {
    return error instanceof DOMException && error.name === "AbortError" ? "cancelled" : null;
  }
  let settled = false;
  return {
    filename,
    async write(blob) {
      const writable = await handle.createWritable();
      // The browser commits the file only on close; abort leaves no partial file.
      try {
        await writable.write(blob);
        await writable.close();
      } catch (error) { await writable.abort().catch(() => undefined); throw error; }
      settled = true;
    },
    async discard() {
      if (settled) return;
      settled = true;
      // Feature checks: getFile() and remove() are not in every browser that has the window.
      if (typeof handle.remove !== "function" || typeof handle.getFile !== "function") return;
      try {
        // A file with bytes may be one the person chose to replace: it is theirs, so it stays.
        if ((await handle.getFile()).size === 0) await handle.remove();
      } catch { /* The file stays; the person loses nothing. */ }
    },
  };
}

/** Writes into the chosen place; a failed write falls back to a download. */
export async function saveToPlace(place: SaveAsPlace | null, blob: Blob, filename: string): Promise<"saved" | "downloaded"> {
  try {
    if (place) {
      await place.write(blob);
      return "saved";
    }
  } catch { await place?.discard(); }
  saveBlobDownload(blob, filename);
  return "downloaded";
}
