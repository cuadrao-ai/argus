export type ReceiptPdf = {
  pageCount: number;
  drawPage: (page: number, canvas: HTMLCanvasElement, scale: number, signal: AbortSignal) => Promise<{ width: number; height: number }>;
  destroy: () => Promise<void>;
};

/** Loaded only when a PDF is opened. The worker is emitted as a separate asset. */
export async function loadReceiptPdf(blob: Blob, signal: AbortSignal): Promise<ReceiptPdf> {
  const { getDocument, GlobalWorkerOptions } = await import("pdfjs-dist");
  signal.throwIfAborted();
  GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
  const data = new Uint8Array(await blob.arrayBuffer());
  signal.throwIfAborted();
  const task = getDocument({ data });
  let disposal: Promise<void> | undefined;
  const abort = () => { void destroy(); };
  const destroy = () => {
    signal.removeEventListener("abort", abort);
    return disposal ??= task.destroy();
  };
  signal.addEventListener("abort", abort, { once: true });
  try {
    const document = await task.promise;
    signal.throwIfAborted();
    return {
      pageCount: document.numPages,
      destroy,
      async drawPage(number, canvas, scale, drawSignal) {
        const page = await document.getPage(number);
        drawSignal.throwIfAborted();
        const size = page.getViewport({ scale: 1 });
        // Bound canvas memory even for unusually large page dimensions.
        const density = Math.min(Math.max(1, scale) * (window.devicePixelRatio || 1), 4, Math.sqrt(16_000_000 / (size.width * size.height)));
        const viewport = page.getViewport({ scale: density });
        // Publish the finished page atomically; a zoom redraw must not clear
        // the visible canvas while text and images are still being drawn.
        const rendered = window.document.createElement("canvas");
        rendered.width = Math.ceil(viewport.width);
        rendered.height = Math.ceil(viewport.height);
        const rendering = page.render({ canvas: rendered, viewport });
        const cancel = () => rendering.cancel();
        drawSignal.addEventListener("abort", cancel, { once: true });
        try {
          await rendering.promise;
          drawSignal.throwIfAborted();
          canvas.width = rendered.width;
          canvas.height = rendered.height;
          canvas.getContext("2d")!.drawImage(rendered, 0, 0);
          return { width: size.width, height: size.height };
        } finally {
          drawSignal.removeEventListener("abort", cancel);
          rendered.width = rendered.height = 0;
        }
      },
    };
  } catch (error) {
    await destroy();
    throw error;
  }
}
