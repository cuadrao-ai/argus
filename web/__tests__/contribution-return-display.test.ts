import { describe, expect, test } from "bun:test";

import {
  displayResultMetricLabel,
  heroDeltaEvidenceView,
  resultMetricDisplayOrder,
} from "@/lib/result-card-display";
import { resultCardPlaygroundFixtures } from "@/lib/result-card-playground-fixtures";

// A recurring plan's return row is its own key with its own name, so a
// consumer keyed on total_return_pct can never silently receive it.
describe("contribution return display contract", () => {
  test("sits in the same slot as a total return row", () => {
    expect(
      resultMetricDisplayOrder({
        key: "contribution_return_pct",
        label: "Return on contributions",
      }),
    ).toBe(
      resultMetricDisplayOrder({
        key: "total_return_pct",
        label: "Total return",
      }),
    );
  });

  test("keeps its own label instead of borrowing Total return", () => {
    expect(
      displayResultMetricLabel({
        key: "contribution_return_pct",
        label: "Return on contributions",
      }),
    ).toBe("Return on contributions");
    expect(
      displayResultMetricLabel(
        { key: "contribution_return_pct", label: "Retorno sobre aportes" },
        undefined,
        { copy: { contributionReturnLabel: "Retorno sobre aportes" } },
      ),
    ).toBe("Retorno sobre aportes");
  });

  test("the hero sub-line names contributions, not total return", () => {
    const dca = resultCardPlaygroundFixtures.find(
      (fixture) => fixture.id === "dca-result",
    );
    expect(dca).toBeDefined();
    const hero = heroDeltaEvidenceView(dca!.result);
    expect(hero.hero.detail).toContain("return on contributions");
    expect(hero.hero.detail).not.toContain("total return");
  });


});
