# Cuadrao website design

The founder approved this presentation through local reviews on October 6 and 7,
2026. This guide records the resulting choices. It specifies the landing pages,
not the Business application or public release readiness.

## Product story

The [MVEE](../../../docs/specs/argus-minimum-viable-ecosystem-experience.md)
owns approved experience. The [master plan](../../../docs/specs/cuadrao-master-plan.md)
contains proposals as well as decisions. The
[coverage record](../../../docs/reports/evidence/cuadrao-owner-vision/coverage.md)
maps those sources to the examples and names excluded capabilities.

Business tells four owner stories:

1. Understand recorded money, accounts, movements and personal/business separation.
2. Plan upcoming payments, budgets, goals, debt and cash outlook.
3. Capture information, review assistant proposals, search records and follow updates.
4. Follow customers, invoices, partial payments and remaining balances.

Receipt review and accountant preparation are supporting tasks. They must not
become the main proposition. All demonstrations use fictional records and show
planned experiences. They do not establish shipped capabilities or integrations.

## Approved appearance

- Preserve the cream canvas, deep green business examples and dark green footer.
- Preserve the sans-serif typography and Cuadrao wordmark.
- Keep the readable cream note seated in the green folio in the Business opening.
- Personal uses ivory and sage. Do not restore the earlier lavender treatment.
- Keep the supplied native Home screenshot as a labelled preview with sample data.
- Keep the founder portrait beside the handwritten Lucas Garcés signature.
- Keep the large footer wordmark hollow with a one-pixel outline and lowered, partly cropped at the bottom. Keep Space Grotesk for headings and Inter for body text.
- Remove the extra footer line "Pensado para los negocios de aquí" and its English equivalent.
- Keep "Las cuentas claras. El negocio, adelante." as the Business footer message.

The founder supplied reference examples for clear hierarchy, readable records,
restrained page structure and broad product coverage. The founder supplied a
LogSnag letter as a reference for a direct personal note. These references do not
authorize copying another product's claims, integrations or customer proof.

## Content and navigation

Spanish leads and every page has an English version. Business and Personal share
one identity. Keep the Business contact action and the link to its interactive
examples. The page covers the full web workspace and the planned mobile companion.

Use direct benefit-led headings. The founder letter is four short paragraphs.
Keep five FAQ questions covering availability, audience, price, boundaries and
the founder conversation. Short readiness labels should remain near demonstrations.
Keep specific limitations at forms and fiscal/export boundaries.

The Business footer links to Contact and Lucas's LinkedIn. The direct email is
on Contact. Do not repeat it in the Business footer. Do not add social account
placeholders while those accounts have no content.

On mobile, Personal signup comes before artwork. Contact presents the introduction,
form and then direct contact/founder details. DOM order and visual order agree.
Header return links keep icon and text on one line and offer a 44px target.

## Example truth and interaction

`owner-example.ts` owns the money and planning records. `sample-data.ts` owns the
invoice example. Derive the RD$30,000 remainder from its RD$48,000 invoice and
RD$18,000 payment. Keep currencies separate. Owner contributions are not sales;
a personally paid business expense does not reduce business cash.

A delayed-payment scenario changes only the estimate. Capture and reminder
confirmation affect examples only. They create no real financial records,
notifications or customer messages. Receipt linking does not create a second expense.

Keep keyboard-operated tabs, query preservation on search return, relevant update
links, expandable receipt/preparation anchors and reduced-motion behavior. Do not
add autoplay, scroll interception, fake progress or decorative working controls.

## Contact and early access

The site is the independent `marketing/` package, not a route of the legacy
`web/` app. Its routes derive from `marketing/lib/site-routes.ts`: Spanish is
unprefixed (`/`, `/personal`, `/contacto`, `/privacidad`) and English lives under
`/en` (`/en`, `/en/personal`, `/en/contact`, `/en/privacy`). The earlier
`/business` paths redirect permanently.

The Business form sends name, email and an optional description. Confirmation
appears only after the service accepts the message, and a failure keeps the
visitor's text beside the direct `hola@cuadrao.ai` address. Personal keeps its
email-only form and approved invitation copy; its confirmation appears only after
the database stores the signup. Both forms link to a privacy page near the
button. Request limits, storage, removal and the availability notice are defined
in the [forms contract](../../../docs/specs/cuadrao-marketing-forms-contract.md).

The browser identity is a provisional Cuadrao mark (a lowercase `c` in the
cream-on-green palette) pending founder review. It is not a permanent logo.

## Integration and publication

Hosts other than the approved public one send `noindex` and a disallow-all
`robots.txt`. Indexing is a runtime setting, not a build setting. Release
settings, cutover and rollback live in the
[launch runbook](../../../docs/runbooks/cuadrao-marketing-launch.md). A successful
merge is not public launch authorization.

Preserve existing application routes, auth, financial services, public receipts,
analytics and saved app-language preferences in `web/`. The marketing package
adds no analytics and stores nothing in the browser.

The [delivery spec](../../../docs/superpowers/specs/2026-10-06-cuadrao-business-website.md)
records the original execution scope. Browser and integration evidence lives in
[the delivery report](../../../docs/reports/evidence/cuadrao-integration-delivery/README.md)
and the [launch evidence](../../../docs/reports/evidence/cuadrao-marketing-launch/README.md).
