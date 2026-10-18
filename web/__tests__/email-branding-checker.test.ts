import { expect, test } from "bun:test";
// @ts-expect-error The standalone Node checker is shared with CI.
import { brandingViolations } from "../../scripts/emails/check-branding.mjs";

test("email branding guard rejects old identity and staging hosts", () => {
  for (const source of ["Argus", "ARGUS", "get-argus.com", "https://arguschat.ai/icon.png", "https://cuadrao-web-staging.onrender.com", "https://staging.cuadrao.ai"]) {
    expect(brandingViolations(source).length).toBeGreaterThan(0);
  }
  expect(brandingViolations("Cuadrao https://cuadrao.ai https://assets.example.test hola@cuadrao.ai")).toEqual([]);
});
