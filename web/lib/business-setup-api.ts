import { z } from "zod";
import { apiFetch } from "./argus-api-transport";

/** `GET /business/setup`: the server's setup steps in order. A step whose feature is off is absent. */
export const businessSetupSchema = z.object({
  steps: z.array(z.object({
    key: z.enum(["created", "fiscal_identity", "receiving_address", "receipt_reading", "team", "whatsapp"]),
    required: z.boolean(),
    done: z.boolean(),
  })),
});
export type BusinessSetup = z.infer<typeof businessSetupSchema>;
export type BusinessSetupStep = BusinessSetup["steps"][number];
export type BusinessSetupStepKey = BusinessSetupStep["key"];

export async function getBusinessSetup(signal?: AbortSignal): Promise<BusinessSetup> {
  return businessSetupSchema.parse(await apiFetch("/business/setup", { signal }));
}
