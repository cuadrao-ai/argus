# Cuadrao business local website review

Built and checked on October 6, 2026. Local preview is at
`http://127.0.0.1:3219/business`. The server is bound to this computer.
This delivery is ready for the founder's design review. It is not published.

## Delivered experience

The Spanish-first landing page explains the proposed value, shows fictional
product data, introduces the founder, and leads to a demo form. English uses
the same layout. Personal has a small coming-soon page. The form validates
entries and displays a local review with an edit action. It sends no request
and reserves no meeting.

The [design guide](../../../../.agent/designs/cuadrao-business/DESIGN.md)
owns agreed direction. The [build spec](../../../superpowers/specs/2026-10-06-cuadrao-business-website.md)
owns routes, flag, implementation boundaries, and Mobbin references.

## Verification

| Check | Result and evidence |
| --- | --- |
| Production build | Passed Next.js build, including its TypeScript check. [Build output](build.txt). |
| Focused regression tests | 83 passed, 0 failed across business route/sample arithmetic, public receipt, and Spanish UI tests. [Test output](tests.txt). |
| HTTP behavior | 20 production-server checks passed. Enabled routes render; disabled and unknown routes return 404. Existing root stays 200 and production dev result-card stays 404. [Results](http-checks.json), [repeatable check](verify-preview.py). |
| Server HTML | All six pages contain headings, route language, and noindex before JavaScript. Demo fields are disabled before hydration to prevent native GET submission. Included in HTTP checks. |
| Form | Empty submission shows three errors and focuses name. Invalid email focuses email. Synthetic valid input opens an honest review. Edit preserves values and restores focus. [Review screenshot](demo-review.jpg). |
| Navigation | Desktop links, ES/EN on the current page, Personal return, mobile menu, initial menu focus, and Escape focus return checked in the browser. |
| Product preview | Mouse and arrow-key tab changes checked. Summary, receivables, and expenses remain illustrative. Accessible chart table has the same sample values. |
| Responsive layout | No page overflow at measured CSS widths 320, 390, 767, and 1440. Spanish and English checked. [Final English measurements](layout-checks.json), [Spanish phone](mobile-spanish.jpg), [English phone](mobile-english.jpg). |
| Motion | Reduced-motion CSS inspected. OS preference emulation was not available in this browser driver. |
| Lint and repository checks | Scoped ESLint passed. Git whitespace checks passed. Modularity budget reported no violations. |
| Data behavior | Source inspection found no fetch, beacon, or persistent browser-storage writes in business components. Browser network packet capture was not performed. |
| Independent review | UI review passed after clarifying form privacy text. Final route-gate review passed. Comment audit inspected 11 files; one redundant comment removed, two Next.js rationale comments kept. |

Browser checks used the local production build and synthetic contact details.
The final source change after that build deleted one redundant comment in
`sample-data.ts`; it changes no runtime behavior. All visual and interaction
evidence remains applicable. Documentation and evidence changes are also inert.

The standalone repository-wide `tsc` command has baseline test typing errors.
This report claims the passing Next.js production TypeScript check only.
No physical-device, Safari, Lighthouse, conversion-rate, or field-performance
claim is made. Those remain separate launch checks.

## Visual comparison ledger

The [four generated concepts](concepts/) translated the inspected Mobbin
references into one Cuadrao direction. They are design references, not final
founder-approved pixels. The rendered pages were inspected against them.

| Area | Rendered result and deliberate differences |
| --- | --- |
| Hero hierarchy | Large two-line serif headline, short explanation, dark demo action, quiet secondary link, development note. [Hero](desktop-hero.jpg) follows [concept](concepts/hero.png). |
| Typography | Georgia display text with self-hosted Inter body and Space Grotesk wordmark. The exact generated serif is not reproduced; this provisional font pair is ready for founder review. |
| Palette and spacing | White canvas, near-black text, pale-gray preview, fine rules, open section spacing. No gradients or decorative card grid. |
| Product preview | Native interactive tabs replace image-only controls. Six chart months, neutral fictional customers, and shared arithmetic replace invented concept details. |
| Process and story | Two-column numbered approach and concise founder section retain the concept hierarchy. Copy describes work in development. Extra generated navigation is omitted. [Rendered](desktop-approach.jpg), [concept](concepts/approach.png). |
| Demo | Explanation sits beside the form and stacks above it on narrow screens. Explicit prototype notice, validation, and review/edit states are real. Language and audience navigation are added. [Rendered](desktop-demo.jpg), [concept](concepts/demo.png). |
| Footer | Oversized Cuadrao lettering is intentionally clipped in its own decorative container. Useful links and the closing action remain readable. [Rendered](desktop-footer.jpg), [concept](concepts/footer.png). |
| Mobile | Menu replaces the desktop links; layout stacks and controls stay usable. An accessible table initially widened the page. Moving the hidden treatment to its wrapper fixed the overflow. |
| Assets and claims | No invented founder portrait, profile link, clients, pricing, employer logos, or published service promises. |

Viewport overrides in the in-app browser produced some white padding outside
the captured page. The recorded DOM widths establish the tested layout sizes;
screenshots are visual evidence, not pixel-parity measurements. Full-page and
superseded screenshots were removed from this evidence set.

## Execution and handoff

The branch is `codex/cuadrao-business-website`, based on integration
`ad7eb9ccb8261456d12ce5a26686682bbce9ae2f`. The initial checkout was
`5e3466672b6e25e9827b15c39b3f3f7053e35d3a`; the intervening integration changes
were documents. This local assignment makes no release-ready or CI claim.

The implementation used one worker for the coupled business UI modules. The
parent owned routing and verification. File ownership was handed back before
the parent made fixes. Read-only context and review work ran independently.
Consumer and runtime backend files were outside the assignment.

The Prove It Works principle changed the final check from build-only to direct
production HTTP and browser verification. That exposed the streaming 404 issue
and the mobile table overflow before handoff.

To restart the preview after its process ends, run from `web`:

```sh
CUADRAO_WEBSITE_PREVIEW=true NEXT_DIST_DIR=.next-business-production bun run start --hostname 127.0.0.1 --port 3219
```

The existing local production output supports that command. To rebuild it, run
`CUADRAO_WEBSITE_PREVIEW=true NEXT_DIST_DIR=.next-business-production bun run build`
with the repository's normal local environment. The flag is server-only and off
by default. No hosted setting changed.

Before publication, choose the real booking destination, review final copy and
company facts, supply the optional portrait/profile link, and approve hosting
and domain configuration. Customer-fit discovery and pricing remain open.
