# Shared footer and page background verification

Owner is `codex/marketing-footer-route-background`. The branch starts at integration `eb54d6f2c7f260012bb1a08780970d16b8bc38b4`, after #1200 landed.

Contact and legal pages rendered a dark footer over transparent `html` and white `body`. The contact regression failed with expected `rgb(23, 43, 38)` and received `rgba(0, 0, 0, 0)`. Native iOS Safari exposed white below that footer. These pages now reuse the Business background marker. The global 404 has no footer; both roots now match its existing `#fafbf8` cream without changing its layout.

The shared footer renders the approved Spanish or English credit on every localized page. Spanish contact/legal credits already existed and are not claimed as a new fix. The English text is `Made with ♥ for the Dominican Republic`. Both languages retain the same grey text and plain heart. No timing CSS changed. The credit remains hidden on small screens; desktop reduced motion shows both texts without animation.

## Reported hover issue

At the reported 1365px desktop width, the original `/personal` reveal passed in both Chromium and WebKit before edits. The copyright moved more than 100px, the credit reached `inset(0px)`, and the 700ms/500ms/100ms timings matched. The report was not reproduced, so this PR does not claim an animation repair. Expanded coverage now checks every localized footer route.

## Verification

- Production build, TypeScript, focused ESLint, diff whitespace and modularity checks passed.
- `footer.spec.ts` and `footer-background.spec.ts`: 66 Chromium tests passed at 1365px and 390px.
- All 12 localized reveal cases passed in WebKit at 1365px.
- Browser checks cover root colors, full-width footer geometry, no horizontal overflow, loaded wordmarks, hover reversal, reduced motion and mobile-hidden credits.
- Native Safari on one iPhone 17e simulator, iOS 27.0 build 24A434, logical width 390px: Contact before/after, English Privacy after, and 404 after. Contact and legal stay dark during bottom swipes; 404 stays cream.
- Read-only hosted check on `https://cuadrao-marketing-staging.onrender.com/personal` after the coordinator confirmed #1200 deployment at `eb54d6f2`: bottom overscroll stays cream. No form submission or service mutation.

Native evidence is simulator Safari, not a physical-phone claim. The original shutdown simulator was the only device booted for this lane. No other simulator was changed.

## Evidence storage

[Relocated artifacts](relocated-artifacts.json) lists exactly 34 PNG/MP4 files introduced by #1197 and #1200, totaling 5,947,133 bytes. Every source and external copy matched SHA-256 before removal from the tracked tree. Site assets and older reports were untouched. Git history is unchanged.

[New verification artifacts](verification-artifacts.json) records the new native recordings and browser screenshots. Binary evidence lives outside the checkout under the shared sprint `footer-artifacts` directory. The old report links now point there. This keeps the checkout smaller but requires access to that local evidence directory.

Model the Domain kept the existing page-background markers and made footer locale the sole credit-copy input. Prove It Works required native Safari swipes and hash comparisons, rather than inferring success from a build.
