import { expect, test } from "bun:test";
import { whatsAppLinkProblem } from "../lib/whatsapp-link-api";

test.each([
  [409, "whatsapp_setup_required", "setup_required"],
  [404, "whatsapp_unavailable", "unavailable"],
  [429, "whatsapp_link_code_rate_limited", "rate_limited"],
  [409, "whatsapp_consent_disclosure_stale", "stale"],
])("link problem %i %s renders the %s state", (status, code, expected) => {
  expect(whatsAppLinkProblem({ status, code })).toBe(expected);
});

test("a network failure is recoverable", () => {
  expect(whatsAppLinkProblem(new Error("network"))).toBe("failed");
});
