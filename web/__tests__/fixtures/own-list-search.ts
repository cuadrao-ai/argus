import { mock } from "bun:test";

/**
 * For a file that drives a list's own search field: what a phone keeps, and what a wide screen keeps with no bar
 * search. business-list-one-search.dom.test.tsx proves the wide screen's loan to the top bar.
 */
export async function keepOwnListSearch() {
  const real = { ...await import("@/components/business-app/foundation/list-search") };
  mock.module("@/components/business-app/foundation/list-search", () => ({ ...real, barSearchAvailable: false, useSearchInBar: () => false }));
}
