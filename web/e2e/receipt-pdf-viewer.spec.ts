import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

// Two real pages with different colored headers and readable synthetic contents.
function twoPagePdf() {
  const stream = (page: number) => `${page === 1 ? "0.1 0.35 0.25" : "0.15 0.25 0.65"} rg 40 650 520 100 re f\n0 0 0 rg BT /F1 24 Tf 50 600 Td (Comprobante de prueba - ${page}/2) Tj 0 -60 Td /F1 16 Tf (Compra de materiales) Tj 0 -40 Td (Total: RD$ 1,180.00) Tj 0 -40 Td (ITBIS: RD$ 180.00) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${stream(1).length} >>\nstream\n${stream(1)}\nendstream`,
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>",
    `<< /Length ${stream(2).length} >>\nstream\n${stream(2)}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => { offsets.push(pdf.length); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(pdf);
}

for (const theme of ["light", "dark"] as const) for (const width of [1440, 390]) for (const kind of ["image", "pdf"] as const) {
  test(`${kind} uses the file viewer at ${width}px in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const diagnostics: string[] = [];
    page.on("console", message => { if (["error", "warning"].includes(message.type())) diagnostics.push(`${message.type()}: ${message.text()}`); });
    page.on("response", response => { if (response.status() >= 400) diagnostics.push(`${response.status()}: ${response.url()}`); });
    const workers: string[] = [];
    page.on("worker", worker => workers.push(worker.url()));
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    const receipt = { ...await source.receipt("rcpt-ferreteria"), media_type: kind === "pdf" ? "application/pdf" : "image/svg+xml", filename: `comprobante.${kind === "pdf" ? "pdf" : "svg"}` };
    await installReceiptBusiness(page, (parts, route) => {
      if (parts[0] === "guide-cards") return Promise.resolve({ dismissed: true });
      if (parts[0] === "setup") return source.setup!();
      if (parts[0] === "drafts" && parts[2] === "dossier") return source.dossier(parts[1]).then(dossier => ({ ...dossier, sources: dossier.sources.map(item => item.kind === "attachment" ? { ...item, media_type: receipt.media_type, filename: receipt.filename } : item) }));
      if (parts[0] !== "receipts") return undefined;
      if (parts.length === 1) return source.receiptPage!("all").then(result => ({ ...result, items: [receipt], activity: { ...result.activity, reading_count: 0, unread_count: 1, pending_review_count: 1, ready_to_review_count: 1, bandeja_attention_count: 1, bandeja_listo_count: 0, bandeja_eliminados_count: 0 } }));
      if (parts[1] !== receipt.id) return undefined;
      if (parts.length === 2) return Promise.resolve(receipt);
      if (parts[2] === "read") return source.markReceiptRead!(receipt.id, route.request().postDataJSON().completion_cursor).then(activity => { receipt.activity = activity; return activity; });
      if (parts[2] === "source" && kind === "pdf") return route.fulfill({ contentType: "application/pdf", body: twoPagePdf() }).then(() => null);
      return undefined;
    }, theme);
    await page.goto("/biz?view=inbox");
    await expect(page).toHaveTitle("Cuadrao");
    await expect(page.getByTestId("reception-row")).toHaveCount(1);
    expect(workers).toHaveLength(0);
    if (kind === "pdf" && width === 1440) {
      await page.getByTestId("reception-original").click();
      await expect(page.getByTestId("receipt-original-source").locator("canvas")).toHaveAttribute("data-page", "1");
      await expect(page.getByTestId("receipt-original-source").locator("iframe")).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("receipt-original-source")).toHaveCount(0);
    }
    await page.getByTestId("reception-row").getByRole("button", { name: "Abrir", exact: true }).click();
    await expect(page.getByTestId("business-record-review")).toBeVisible();
    const original = page.getByTestId("receipt-original-source");
    // Below the desktop stop the record is a full page and its file lives in the Documento tab.
    if (width === 390) await page.getByRole("tab", { name: "Documento", exact: true }).click();
    const viewer = original.getByTestId("receipt-viewer");
    await expect(viewer).toBeVisible();
    await expect(original.locator("iframe")).toHaveCount(0);
    await expect(viewer.getByTestId("receipt-viewer-toolbar")).toHaveCount(1);
    if (kind === "pdf") {
      const canvas = viewer.locator("canvas");
      await expect(canvas).toHaveAttribute("data-page", "1");
      const first = await canvas.evaluate(node => (node as HTMLCanvasElement).toDataURL());
      expect(await canvas.evaluate(node => {
        const canvas = node as HTMLCanvasElement;
        const readback = document.createElement("canvas");
        readback.width = canvas.width; readback.height = canvas.height;
        const context = readback.getContext("2d", { willReadFrequently: true })!;
        context.drawImage(canvas, 0, 0);
        const pixel = context.getImageData(Math.round(canvas.width / 2), Math.round(canvas.height / 8), 1, 1).data;
        return pixel[1] > pixel[0] && pixel[1] > pixel[2] && pixel[3] === 255;
      })).toBe(true);
      expect(workers.some(url => url.includes("pdf.worker") && new URL(url).origin === new URL(page.url()).origin)).toBe(true);
      await canvas.evaluate(node => {
        const canvas = node as HTMLCanvasElement;
        const observer = new MutationObserver(() => {
          observer.disconnect();
          const readback = document.createElement("canvas");
          readback.width = canvas.width; readback.height = canvas.height;
          const context = readback.getContext("2d", { willReadFrequently: true })!;
          context.drawImage(canvas, 0, 0);
          const pixels = context.getImageData(0, Math.round(canvas.height * 0.2), canvas.width, Math.round(canvas.height * 0.3)).data;
          let ink = 0;
          for (let i = 0; i < pixels.length; i += 4) if (pixels[i] < 100 && pixels[i + 1] < 100 && pixels[i + 2] < 100 && pixels[i + 3] === 255) ink++;
          canvas.dataset.completeRedraw = String(ink > 200);
        });
        observer.observe(canvas, { attributes: true, attributeFilter: ["width", "height"] });
      });
      await viewer.getByRole("button", { name: "Acercar", exact: true }).click();
      await expect(canvas).toHaveAttribute("data-complete-redraw", "true");
      await viewer.getByTestId("receipt-image-zoom").press("0");
      await viewer.getByRole("button", { name: "Página siguiente", exact: true }).click();
      await expect(canvas).toHaveAttribute("data-page", "2");
      expect(await canvas.evaluate(node => (node as HTMLCanvasElement).toDataURL())).not.toBe(first);
      await expect(viewer.getByRole("button", { name: "Página siguiente", exact: true })).toBeDisabled();
      await viewer.getByRole("button", { name: "Página anterior", exact: true }).click();
      await expect(canvas).toHaveAttribute("data-page", "1");
      expect(await canvas.evaluate(node => {
        const canvas = node as HTMLCanvasElement;
        const readback = document.createElement("canvas");
        readback.width = canvas.width; readback.height = canvas.height;
        const context = readback.getContext("2d", { willReadFrequently: true })!;
        context.drawImage(canvas, 0, 0);
        const pixels = context.getImageData(0, Math.round(canvas.height * 0.2), canvas.width, Math.round(canvas.height * 0.3)).data;
        let ink = 0;
        for (let i = 0; i < pixels.length; i += 4) if (pixels[i] < 100 && pixels[i + 1] < 100 && pixels[i + 2] < 100 && pixels[i + 3] === 255) ink++;
        return ink;
      }), "a completed page includes its text, not only its colored header").toBeGreaterThan(200);
    } else {
      await expect(viewer.getByRole("img", { name: "Recibo original" })).toBeVisible();
      await expect(viewer.getByRole("button", { name: "Página siguiente", exact: true })).toHaveCount(0);
      expect(workers).toHaveLength(0);
    }
    await viewer.scrollIntoViewIfNeeded();
    if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/${kind}-${width}-${theme}.png` });
    await viewer.getByRole("button", { name: "Girar a la derecha", exact: true }).click();
    await expect(viewer.getByTestId("receipt-image-zoom")).toHaveAttribute("data-rotation", "90");
    await viewer.getByRole("button", { name: "Pantalla completa", exact: true }).click();
    const overlay = page.getByTestId("receipt-viewer-overlay");
    await expect(overlay).toBeVisible();
    await expect(overlay.getByRole("link", { name: "Abrir original" })).toHaveAttribute("href", /^blob:/);
    if (kind === "pdf") await expect(overlay.locator("canvas")).toHaveAttribute("data-page", "1");
    await page.keyboard.press("Escape");
    await expect(overlay).toHaveCount(0);
    await test.info().attach("browser-diagnostics", { body: JSON.stringify(diagnostics, null, 2), contentType: "application/json" });
    if (process.env.CUADRAO_RECORD_EVIDENCE_DIR) await writeFile(`${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/${kind}-${width}-${theme}-diagnostics.json`, JSON.stringify(diagnostics, null, 2));
    expect(errors).toEqual([]);
    expect(diagnostics).toEqual([]);
  });
}
