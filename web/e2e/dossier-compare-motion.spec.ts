import { expect, test, type Locator } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import type { BusinessComparedDocument } from "../lib/business-dossier";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

function receipt(id: string): BusinessComparedDocument {
  const received_at = "2026-11-03T12:00:00Z";
  return {
    draft_id: id, state: "open", received_at, approved_at: null,
    counterparty: "Comercio de prueba", occurred_on: "2026-11-03",
    amount: "100.00", currency: "DOP", fiscal_number: null,
    file: { connection_id: id, filename: id + ".svg", media_type: "image/svg+xml", channel: "web", received_at },
  };
}

function trackPreview(frame: Locator) {
  return frame.evaluateHandle(element => {
    const heights = new Set<number>();
    const fades = new Set<number>();
    let request: number;
    function sample() {
      heights.add(element.getBoundingClientRect().height);
      for (const animation of element.getAnimations({ subtree: true })) {
        const effect = animation.effect as KeyframeEffect;
        if (effect.getKeyframes().some(frame => frame.opacity !== undefined)) {
          fades.add(Number(effect.getTiming().duration));
        }
      }
      request = requestAnimationFrame(sample);
    }
    sample();
    return () => {
      cancelAnimationFrame(request);
      return { heights: [...heights], fades: [...fades] };
    };
  });
}

for (const motion of ["no-preference", "reduce"] as const) {
  test(`Comparar keeps the current image until the saved image loads with ${motion} motion`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.emulateMedia({ reducedMotion: motion });
    const current = receipt("actual");
    const saved = receipt("anterior");
    let release!: () => void;
    const held = new Promise<void>(resolve => { release = resolve; });
    await installReceiptBusiness(page, ([resource, id, action], route, source) => {
      if (resource === "drafts" && action === "dossier") return source.dossier(dossierFixtureIds.ready).then(base => ({
        ...base, draft_id: current.draft_id, sources: [], listo_gaps: ["duplicate"],
        bandeja_group: { group: "attention", reason: "duplicate", label: "needs_attention" },
        duplicate_candidates: [{
          draft_id: saved.draft_id, version: 1, basis: "read_facts", decisions: [],
          comparison: { document: current, other: saved, differences: ["file"], recommendation: null },
        }],
      }));
      if (resource === "receipts" && action === "source") {
        const body = `<svg xmlns="http://www.w3.org/2000/svg" width="${id === "actual" ? 320 : 440}" height="440"><rect width="100%" height="100%" fill="white"/><text x="24" y="56" font-size="24">Recibo ${id}</text></svg>`;
        return (id === saved.draft_id ? held : Promise.resolve()).then(() => route.fulfill({ body, contentType: "image/svg+xml" })).then(() => null);
      }
    });

    await page.goto("/biz?draft=actual");
    await page.getByTestId("dossier-reason").click();
    const source = page.getByTestId("receipt-review-source");
    const image = source.locator("img").first();
    await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(320);
    const original = await image.getAttribute("src");
    const frame = await source.boundingBox();
    expect(frame!.height).toBeGreaterThan(0);
    const sample = await trackPreview(source);
    const requested = page.waitForRequest(request => request.url().endsWith("/receipts/anterior/source"));
    await page.getByRole("radio", { name: "Guardado antes" }).click();
    await requested;
    try {
      await page.screenshot({ path: testInfo.outputPath("compare-waiting.png") });
      expect(await page.locator("img").evaluateAll((images, src) => images.some(img =>
        img.getAttribute("src") === src && img.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })), original)).toBe(true);
    } finally { release(); }
    const next = source.locator("img").filter({ visible: true }).last();
    await expect.poll(() => next.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(440);
    await expect.poll(() => page.evaluate(() =>
      document.getAnimations().filter(animation => (animation.effect as KeyframeEffect)?.getKeyframes().some(frame => frame.opacity !== undefined)).length)).toBe(0);
    const { heights, fades } = await sample.evaluate(finish => finish());
    expect(heights).toEqual([frame!.height]);
    expect(await source.boundingBox()).toEqual(frame);
    if (motion === "reduce") expect(fades).toEqual([]);
    else expect(fades).toContain(200);
  });
}
