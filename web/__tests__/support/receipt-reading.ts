import type { ReceiptReading } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";

/** A synthetic server whose workspace and mutation share one reading setting. */
export function withReceiptReading(initial: ReceiptReading | null): Pick<BusinessDataSource, "workspace" | "setReceiptReading"> {
  const fixture = createFixtureBusinessDataSource();
  let reading = initial;
  return {
    workspace: async () => ({ ...await fixture.workspace(), receipt_reading: reading }),
    setReceiptReading: async (snapshot, enabled) => (reading = { ...snapshot, enabled }),
  };
}
