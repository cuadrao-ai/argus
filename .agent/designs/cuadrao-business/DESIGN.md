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
- Preserve the Cuadrao wordmark.
- Headings use Georgia on every page, with Noto Serif as the named backup. Body text uses Inter. The logo and the large footer word use Space Grotesk. `--font-heading` in `marketing/app/globals.css` owns the heading font.
- Keep the founder portrait beside the handwritten Lucas Garcés signature.
- Keep the large footer wordmark hollow with a one-pixel outline and lowered, partly cropped at the bottom.
- Remove the extra footer line "Pensado para los negocios de aquí" and its English equivalent.
- Keep "Las cuentas claras. El negocio, adelante." as the Business footer message.

The founder supplied reference examples for clear hierarchy, readable records,
restrained page structure and broad product coverage. The founder supplied a
LogSnag letter as a reference for a direct personal note. These references do not
authorize copying another product's claims, integrations or customer proof.

## Content and navigation

Spanish leads and every page has an English version. The landing order is hero,
product scene, cards section, "Cómo funciona", "Tu contable", founder letter, FAQ,
closing band and footer.

The header holds the logo, language, sign in and the contact button. It has no
audience link, and no features menu until feature pages exist. The phone menu keeps
its Escape key, focus trap and scroll lock.

Say "contable", not "contador", and "factura" unless the object is a receipt in a
drawer.

Use direct benefit-led headings. The founder letter is four short paragraphs.
Keep five FAQ questions covering availability, audience, price, boundaries and
the founder conversation. One answer is open at a time and the first starts open.
Clicking the open question closes it. The open answer sits on a soft 16px card, and
the list has no divider lines. Short readiness labels should remain near
demonstrations.
Keep specific limitations at forms and fiscal/export boundaries.

The Business footer links to the page sections, Contact, the direct email, Lucas's
LinkedIn and the legal pages. Do not add social account placeholders while those
accounts have no content.

On mobile, Contact presents the introduction,
form and then direct contact/founder details. DOM order and visual order agree.
Header return links keep icon and text on one line and offer a 44px target.

## Example truth and interaction

Examples use sample records. Derive the RD$30,000 remainder from the RD$48,000
invoice and RD$18,000 payment. Keep currencies separate.

The founder approved a scroll-led product scene on November 1, 2026. It may show
scripted status changes, a sample cursor and a dock that links to the stages.
Scrolling stays native: never intercept the scroll. Every animation has a
reduced-motion state. Phones show the scene as one still end picture, skip the
cards section, and play the WhatsApp chat as it enters the screen. The founder chose
not to add an illustrative label to the scene. The FAQ states that the examples
are planned and use fictional data, so keep that sentence.

The scene shows 15 November 2026 until that day passes, then the visitor's own date.
It closes the month before the date it shows. It shows no year, and the time stays
at 10:24.

Facturar stays "En preparación" and is not a link until e-CF issuing works in
production.

Examples create no real records, notifications or customer messages. Do not add
autoplay or fake progress outside the scene.

## Contact

The site is the independent `marketing/` package, not a route of the legacy
`web/` app. Its routes derive from `marketing/lib/site-routes.ts`: Spanish is
unprefixed (`/`, `/contacto`, `/privacidad`) and English lives under
`/en` (`/en`, `/en/contact`, `/en/privacy`). The earlier `/business` and
`/personal` paths redirect permanently.

The Business form sends name, email and an optional description. Confirmation
appears only after the service accepts the message, and a failure keeps the
visitor's text beside the direct `hola@cuadrao.ai` address. The form links to a
privacy page near the button. Request limits are defined in the
[forms contract](../../../docs/specs/cuadrao-marketing-forms-contract.md).

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
