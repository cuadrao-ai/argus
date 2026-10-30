import type { Request } from "@playwright/test";

type SyntheticBusinessRoute = {
  request(): Pick<Request, "url" | "method" | "postDataJSON">;
  fulfill(options: { json: unknown }): Promise<void>;
};

export async function fulfillSyntheticBusinessFallback(route: SyntheticBusinessRoute): Promise<void> {
  const path = new URL(route.request().url()).pathname.split("/business/")[1];
  throw new Error(`Unmapped synthetic endpoint ${path}`);
}
