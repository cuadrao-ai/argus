# Cuadrao business website delivery

> This spec retains the first local draft as implementation history. Its demo wording and editorial visual
> choices are under review. The current conversation CTA and approved design
> delivery sequence live in the [Business design guide](../../../.agent/designs/cuadrao-business/DESIGN.md).

Deliver a polished local business landing page and prototype demo journey.
Founder authorized implementation October 6 after the discussion recorded in
the [working design guide](../../../.agent/designs/cuadrao-business/DESIGN.md).

## October 7 delivery amendment

The founder approved opening and merging one labelled PR into
`codex/private-alpha-next` after review and checks pass. This authorizes the
integration landing routine, not deployment or public activation.

The [current design guide](../../../.agent/designs/cuadrao-business/DESIGN.md)
supersedes the initial visual, content and form inventory below. The delivered
site includes the full owner vision, five FAQ answers, the founder signature,
ivory/sage Personal and the filled lowered footer. The extra local-business
footer line is removed. Contact requires name and email; description is optional.

Personal is an email-only early-access presentation. Capture remains unavailable
with an honest HTTP 503 response. The founder selected existing Supabase for
follow-up #882; no SQLite runtime or storage is delivered. #881 owns Business
contact delivery; #880 owns public launch activation. Do not close those issues
with this presentation PR.

Preserve all approved copy and working sample interactions. Verify the combined
integration tree, route-off behavior, existing app language/public receipts and
both website locales. Record final review, checks, source identity and screenshots
in [delivery evidence](../../reports/evidence/cuadrao-integration-delivery/README.md).

## 1. Why

The [MVEE](../../specs/argus-minimum-viable-ecosystem-experience.md#consumer-and-business-launch-boundary)
separates Business web from the consumer release. This assignment gives the
founder a credible first door for business outreach, while backend work and
customer discovery continue. It delivers no business application capabilities.

## 2. Locked decisions

1. Spanish leads. Include a complete English alternative using the same layout.
2. Build in existing Next.js, React and TypeScript, with route-scoped CSS.
3. Local preview lives at `/business`, with `/business/demo` and
   `/business/personal`. English equivalents begin `/business/en`.
4. Preserve existing `/`, auth, chat, consumer/native, API and persistence.
5. A server-only `CUADRAO_WEBSITE_PREVIEW=true` enables these routes. They return
   404 by default in every environment; all preview pages declare noindex.
6. Reuse self-hosted Inter and Space Grotesk; Georgia supplies editorial serif
   headlines for this review. This font choice is provisional until founder review.
7. Navigation, hero, illustrative product tabs, open benefits, numbered approach,
   brief founder section, two FAQs, final demo CTA and cropped wordmark form one page.
8. Product preview data is explicitly fictional and stored in one sample-data
   module. Views derive totals from those samples. No finance API calls.
9. Demo form validates locally and shows a review state, never a sent/booked
   state. No fetch, storage, analytics, email, account or calendar integration.
10. Name, business and email are required; a short description is optional.
    Invalid fields have inline errors and focus goes to the first error.
    Review preserves the entered values for editing. The application sends nothing
    and writes no persistent storage; browser history may restore an in-memory view.
11. Personal is only a coming-soon skeleton with a return to Business.
12. Missing portrait and profile links are omitted. Founder text is draft copy
    based only on supplied facts, with no employer logos or endorsements.

## 3. Reserved scope

- Public hosting, root-domain routing, real booking, collection and retention of
  leads, pricing, testimonials, business backend and native delivery remain later work.
- No model/provider calls other than the requested design workflow. No migrations,
  hosted settings, new analytics or production flags are changed.

## 4. Contract gates

- Design guide owns the direction; this spec owns this bounded implementation.
- `web/lib/business-site.ts` owns preview routing, locale and enablement.
- New `web/app/business/[[...path]]` route and `web/components/business` own UI.
- `web/proxy.ts` rejects disabled/unknown Business routes before response streaming
  so their HTTP status is 404. It uses the same route and enablement owner above.
- A narrow existing I18nProvider exception lets this server-rendered marketing
  route render before client initialization and sets its language without changing
  the user's saved app preference. Existing routes retain their behavior.
- `web/.env.local.example` documents the default-off preview. No API/data contract changes.

## 5. Execution contract

Worker branch: `codex/cuadrao-business-website`.
Fetched integration base: `ad7eb9ccb8261456d12ce5a26686682bbce9ae2f`.
The earlier detached checkout was fast-forwarded from `5e3466672b6e25e9827b15c39b3f3f7053e35d3a`;
the intervening changes were product documents, with no runtime/UI overlap.

The founder requests a local review first. This assignment stops at a running
local preview and committed reviewable code; publishing a PR or deployment is
not needed to approve the look. Future delivery is one PR to integration, with
founder merge authority and normal exact-head gates retained.

Verification: production build, TypeScript, focused lint; route/locale/gate and
sample arithmetic tests; browser checks at desktop, tablet and narrow/mobile
widths in Spanish and English. Exercise menu, product tabs, FAQ, form errors,
review/edit, Personal return, keyboard access and reduced motion. Confirm no
horizontal overflow, no lead transmissions, SSR content and noindex. Retain
screenshots and a concise comparison ledger under `docs/reports/evidence/cuadrao-business`.

## 6. Stop conditions

Stop affected work if it needs live lead collection, hosted changes, consumer
route replacement, fiscal/banking claims, or an unresolved financial contract.
Continue independent local design work. Missing portrait/domain/calendar is not
a blocker. No external service setup is needed for the local form.

## 7. Design implementation inventory

The four [concept images](../../reports/evidence/cuadrao-business/concepts/)
were generated with the built-in Image Gen tool under the approved direction.
They are implementation references, not a claim of founder approval of final pixels.

- White #fff canvas, near-black #20211f text/actions, neutral #f5f5f3 preview/footer,
  gray rules. No gradients, glow, stock photographs or decorative icon grids.
- Maximum content width 1180px; generous 96–120px section rhythm. Editorial
  serif headings, Inter body, Space Grotesk wordmark. 6px action corners.
- Hero headline: “Tu negocio, claro y cuadrao.” Support: “Menos papeles sueltos.
  Más claridad sobre lo que entra, lo que sale y lo que falta por cobrar.”
  Actions: “Agenda una demo”, “Explora la idea”. Stage: “En desarrollo, contigo
  desde el principio.” Header: cuadrao, Business, Personal, Cómo funciona,
  Nosotros, Agenda una demo. A small ES/EN switch fulfills language support.
- Product preview is native HTML, not a screenshot. Tabs are real controls;
  decorative sample chrome is not presented as working application navigation.
- Middle: three open columns, then two columns for process copy and numbered rows.
- Lower: concise founder copy, native FAQ disclosures, closing CTA, footer links
  and oversized wordmark cropped only inside a decorative container.
- Demo: editorial left column, local-only notice and labeled form on the right;
  stacks on mobile. Native keyboard focus, visible errors and a review state.
- Mobile: header brand and accessible menu, no hidden primary content; preview
  metrics/grid simplify naturally, form controls at least 44px high, footer crop
  scales with width. Avoid horizontal page scrolling.
- Personal: same shared shell with a quiet lilac surface and short forthcoming
  message; no signup promise, app download, or TestFlight link.

Intentional concept corrections: omit the extra header invented in approach.png;
omit the fake “Ver todo” preview link; replace image-generated client names with
clearly fictional neutral sample labels; derive all sample totals. Use benefit
copy as design intent, not a shipped capability claim. Do not render the mobile
inset as page content. Biography, typography and final copy remain reviewable.

## Sources

Authority: working design guide, PRODUCT, MVEE, architecture and execution board.
Mobbin images were inspected directly on October 6:

- Editorial reference site: editorial restraint, clear hierarchy.
- [Revolut Business](https://mobbin.com/sites/sections/84f53af0-8825-4816-ab6f-0220478a4e81): Personal/Business entrances.
- [Ramp demo](https://mobbin.com/sites/sections/aa950d43-7969-42f3-a11b-f0890c66fdae): explain the conversation beside the action.
- Founder story reference: concise human context.
- Live reference site: oversized cropped footer, checked in browser.

These references support design judgment; Mobbin did not supply ranking,
conversion, or trend-performance evidence. No such claims are made.
