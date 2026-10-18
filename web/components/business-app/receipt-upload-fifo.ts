type WaitingUpload = { key: string; target: string; status: string };

/**
 * One drain, arrival order. `next` is read again after each file, so a file
 * that arrives during a run joins the tail. A thrown `run` does not drop the
 * files behind it.
 */
export async function runFifo<T>(next: () => T | undefined, run: (item: T) => Promise<void>): Promise<void> {
  for (;;) {
    const item = next();
    if (item === undefined) return;
    try {
      await run(item);
    } catch {
      // One file's failure is that file's. The files behind it still upload.
    }
  }
}

/**
 * The next file this drain should upload.
 * Files already queued when save started upload in order.
 * A file added after that joins the tail.
 * A failed file uploads only when this save explicitly included it, and only once.
 */
export function nextWaitingUpload<T extends WaitingUpload>(
  items: readonly T[],
  target: string,
  attempted: ReadonlySet<string>,
  seeded: ReadonlySet<string>,
  presentAtStart: ReadonlySet<string>,
): T | undefined {
  return items.find((item) => {
    if (item.target !== target || attempted.has(item.key)) return false;
    if (item.status === "failed") return seeded.has(item.key);
    if (item.status !== "queued") return false;
    return seeded.has(item.key) || !presentAtStart.has(item.key);
  });
}
