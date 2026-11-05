# Font provenance

The same upstream revisions as the mobile design lock, in Android-compatible TTF
format. Files are unmodified; the adjacent SIL OFL licenses apply.

- Inter 4.2: [upstream revision](https://github.com/rsms/inter/tree/353b61b9f4430d5f420d56605a6e7993e0941470), `docs/font-files/InterVariable.ttf`.
- Space Grotesk 2.0.0: [upstream revision](https://github.com/floriankarsten/space-grotesk/tree/7220f5d04813fe83babe76d4fd23e02275021280), `fonts/ttf/SpaceGrotesk[wght].ttf`.

These existing licensed assets are reused from reference #730 without touching
its shared application or build configuration. Android font resources require
TTF; this prototype does not download fonts at runtime.
