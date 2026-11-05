import assert from "node:assert/strict";
import { test } from "bun:test";
import { amountColumnSize, signedAmountText } from "@/components/business-app/transacciones/transacciones-parts";

test("money column grows for the exact signed display, including foreign currency", () => {
  const short = { amount: "24.00", currency: "DOP" };
  const large = { amount: "-123456789012345.67", currency: "USD" };
  const smallSize = amountColumnSize([short], "DOP", "es-419");
  const largeSize = amountColumnSize([short, large], "DOP", "es-419");
  assert.equal(smallSize.units, 0, "ordinary values keep the existing 136px column");
  assert.equal(smallSize.minTableWidth, "1200px", "detail badges retain their own space");
  assert.ok(largeSize.units > 20, "the currency, sign and full exact number get space");
  assert.match(signedAmountText(large, "DOP", "es-419"), /123,456,789,012,345\.67/);
  assert.match(signedAmountText(large, "DOP", "es-419"), /^−US\$/);
  assert.match(largeSize.minTableWidth, /1088px/);
});
