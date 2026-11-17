import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Every dossier and side panel closes through AdaptivePanel: a click beside it, Escape, its X, and on a
 * phone system back. A screen that adds its own Escape, outside-press listener or focus-on-close drifts
 * from the rest, which is how the dossiers came to close three different ways. Each screen here draws the
 * shared panel (or hands its records to the one that does) and keeps none of that code of its own.
 */

const WEB_ROOT = join(import.meta.dir, "..");

const SCREENS: { screen: string; file: string; draws: "panel" | "record tray" }[] = [
  { screen: "Bandeja document and Registros record", file: "components/business-app/BusinessPanel.tsx", draws: "panel" },
  { screen: "Actividad, which opens its records in the Bandeja tray", file: "components/business-app/actividad/ActivityDraft.tsx", draws: "record tray" },
  { screen: "Inicio setup dossier", file: "components/business-app/inicio/HomeSetup.tsx", draws: "panel" },
  { screen: "Recepción original", file: "components/business-app/recepcion/ReceptionOriginal.tsx", draws: "panel" },
  { screen: "Correo de recibos history", file: "components/business-app/BusinessEmailDeliveries.tsx", draws: "panel" },
  { screen: "Conciliación movement tray", file: "components/business-app/transacciones/TransaccionesTray.tsx", draws: "panel" },
  { screen: "Registros notes and attachments", file: "components/business-app/transacciones/RecordsAnnotationsPreview.tsx", draws: "panel" },
  { screen: "Facturación invoice dossier", file: "components/business-app/invoicing/InvoiceDossier.tsx", draws: "panel" },
  { screen: "Facturación invoice editor", file: "components/business-app/invoicing/InvoiceEditor.tsx", draws: "panel" },
  { screen: "Facturación customer dossier", file: "components/business-app/invoicing/CustomerDossier.tsx", draws: "panel" },
  { screen: "Facturación schedule dossier", file: "components/business-app/invoicing/ScheduleDossier.tsx", draws: "panel" },
  { screen: "Facturación connected workspace", file: "components/business-app/invoicing/ConnectedInvoicingWorkspace.tsx", draws: "panel" },
  { screen: "Facturación currency breakdown", file: "components/business-app/invoicing/InvoiceResultsSummary.tsx", draws: "panel" },
];

/** Escape handling, a document or window press listener, or focus put back by hand when a panel closes. */
const OWN_CLOSE = [
  /["']Escape["']/,
  /addEventListener\(\s*["'](?:pointerdown|mousedown|click|keydown)["']/,
  /(?:returnFocusRef|trigger|opener)\.current\?\.focus\(\)/,
];

describe("every dossier closes through the shared panel", () => {
  for (const { screen, file, draws } of SCREENS) {
    test(`${screen} uses the shared owner and keeps no close code of its own`, () => {
      const source = readFileSync(join(WEB_ROOT, file), "utf-8");
      if (draws === "panel") expect(source).toMatch(/<AdaptivePanel\b/);
      else {
        expect(source).not.toMatch(/<(?:AdaptivePanel|BottomSheet)\b[^>]*onClose/);
        expect(source).toMatch(/openPanel\(target\)/);
      }
      for (const pattern of OWN_CLOSE) expect(source).not.toMatch(pattern);
    });
  }

  test("the Registros movement table leaves Escape to the shared tray", () => {
    const source = readFileSync(join(WEB_ROOT, "components/business-app/transacciones/TransaccionesTable.tsx"), "utf-8");
    expect(source).not.toMatch(/Escape/);
  });
});
