# Cuadrao hollow footer

The large decorative footer wordmark uses a transparent fill and a one-pixel outline. Space Grotesk, Inter, footer crop, and vertical position are unchanged.

Integration base: `44b5a3ef6173bae848edec989770e0552d67e6ca`.

Validation on the candidate application tree:

- Production webpack build and TypeScript passed.
- Browser checks passed on Business and Personal in Spanish and English, at 390 and 1440 pixels. Screenshots and computed styles are in this directory.
- No horizontal page overflow appeared. The outline is one pixel and the fill is transparent.
- Modularity budget and whitespace checks passed.
- No API, forms, runtime, configuration, or font changes. No new automated tests are needed for this decorative CSS change.

CSS SHA-256: `f546e99adc0254934404d2ee09680df5ca8e3b4611f4e1790e2705581fbd6e6f`.

The final review must revalidate this hash against the PR head.
