import type { BusinessDataSource } from "./business-data";
import type { ReceiptDetail } from "@/lib/business-api";

/** The owner's bind action: move the binding, prepare again, read the result. Each step's detail is shown as it arrives. */
export async function rebindAndPrepare(source: Pick<BusinessDataSource, "rebindReceipt" | "prepareReceipt" | "receipt">, id: string, show: (detail: ReceiptDetail) => void): Promise<void> {
  show(await source.rebindReceipt(id));
  await source.prepareReceipt(id);
  show(await source.receipt(id));
}
