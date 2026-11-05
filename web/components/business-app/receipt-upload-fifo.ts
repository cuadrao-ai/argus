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
