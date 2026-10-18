import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { renderBusinessTransferEmail, type TransferEmailVariant } from "../../marketing/lib/email/business-transfer";
import { assertEmailPresentation } from "./helpers/email-presentation";

test("Python mail artifact derives from the shared canonical renderer", () => {
  const artifact = JSON.parse(readFileSync(new URL("../../src/argus/domain/business/business_transfer_email.generated.json", import.meta.url), "utf8"));
  const { assetOrigin, postalAddress, ...data } = artifact.tokens;
  for (const variant of ["requested", "declined", "acceptedOwner", "acceptedTarget", "withdrawn"] satisfies TransferEmailVariant[]) {
    const rendered = renderBusinessTransferEmail(variant, data, { assetOrigin, postalAddress });
    expect(artifact.templates[variant]).toEqual(rendered);
    assertEmailPresentation(rendered.html,rendered.text);
  }
});
