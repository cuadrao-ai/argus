import { expect, test } from "bun:test";
import { renderAccountEmail } from "../server/emails/account-layout.generated";
import { renderBusinessClosedEmail } from "../../marketing/lib/email/business-closed";
import { EMAIL_TEMPLATE_SLOTS, renderTemplateSlot } from "../../marketing/lib/email/template-slots";
import { assertEmailPresentation } from "./helpers/email-presentation";
import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();

for (const slot of Object.keys(EMAIL_TEMPLATE_SLOTS) as Array<keyof typeof EMAIL_TEMPLATE_SLOTS>) {
  test(`disabled slot ${slot} HTML/plain snapshot and light/dark AA`, () => {
    const rendered = renderTemplateSlot(slot, {preview: true});
    expect(rendered).toMatchSnapshot();
    assertEmailPresentation(rendered.html, rendered.text);
  });
}
test("Business close HTML/plain snapshot and light/dark AA", () => {
  const rendered = renderBusinessClosedEmail({businessName: "Tienda", ownerName: "Ana", closedDate: "17/10/2026", purgeDate: "16/11/2026"});
  expect(rendered).toMatchSnapshot();
  assertEmailPresentation(rendered.html, rendered.text);
});
test("presentation checker catches low contrast in each mode and legacy branding", () => {
  const rendered = renderAccountEmail({title: "Cuenta", paragraphs: ["Mensaje"]});
  expect(() => assertEmailPresentation(rendered.html.replaceAll("color:#172b26", "color:#ffffff"), rendered.text)).toThrow("contrast");
  expect(() => assertEmailPresentation(rendered.html.replaceAll(".copy{color:#fafbf8!important}", ".copy{color:#172b26!important}"), rendered.text)).toThrow("contrast");
  for (const forbidden of ["Argus", "get-argus.com", "cuadrao-web-staging.onrender.com"]) {
    expect(() => assertEmailPresentation(rendered.html, forbidden)).toThrow("Legacy branding");
  }
});
