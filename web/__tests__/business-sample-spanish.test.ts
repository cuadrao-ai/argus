import { describe, expect, test } from "bun:test";

import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

// Words that only an English sample would show a Spanish reader in the preview. Merchant and people names stay as they are.
const ENGLISH = /\b(account|card|sample|receipt|how was|paid|other human|via)\b/i;

describe("the preview's sample reads in Spanish", () => {
  test("the sample accounts have natural Spanish names", async () => {
    const source = createFixtureBusinessDataSource();
    const { accounts } = await source.workspace();
    expect(accounts.map((account) => account.nickname)).toEqual(["Cuenta corriente", "Tarjeta del negocio"]);
  });

  test("a sample record's business, question and history say nothing in English", async () => {
    const source = createFixtureBusinessDataSource();
    const dossier = await source.dossier(dossierFixtureIds.unknown);
    const shown = [dossier.space_name, ...dossier.questions.map((question) => question.prompt), ...dossier.history.map((entry) => entry.actor.display_name ?? "")];
    expect(shown.filter((text) => ENGLISH.test(text))).toEqual([]);
  });

  test("the sample receipt image is labelled in Spanish", async () => {
    const source = createFixtureBusinessDataSource();
    const [first] = await source.receipts("inbox");
    const image = await (await source.receiptSource(first.id)).text();
    expect(image).toContain("DATOS DE MUESTRA");
    expect(image).not.toContain("SAMPLE DATA");
  });
});
