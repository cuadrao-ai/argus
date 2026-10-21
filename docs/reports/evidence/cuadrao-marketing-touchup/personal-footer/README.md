# Personal footer image sequence

Superseded by the founder-requested [static wordmark ending](../personal-footer-wordmark/README.md). This folder retains the rejected trial as historical evidence.

The founder requested a Granola-inspired reveal on Personal only. This iteration uses the existing founder-supplied dressmaker and artisan photos. The two-photo pair on Business stays unchanged. There are no player controls or continuous loops.

## Design decision

Two read-only sketches compared a finite CSS photo swap with a frame selected by pull distance. Both use the existing FooterMotion owner and a Personal presentation option. The independent judge preferred distance selection because a 600 ms timed sequence would compete with the accepted 240 ms idle delay. The parent retained the finite sequence but shortened it to 320 ms, with the second photo visible by 220 ms. This preserves the accepted return timing and lets a brief gesture show both photos without requiring a particular pull distance. The existing 500 ms return remains.

The Model the Domain principle kept geometry in the existing reveal value. One attribute triggers the finite CSS effect and clears once the strip closes. Continued input does not restart the image swap. Reduced motion keeps the ending still. A new carousel, animation library, media file, or time-driven JavaScript loop was unnecessary.

The comparison uses two same-model sketches, so model diversity was reduced. One writer held the existing Marketing branch during implementation. The parent owns preview changes, verification, and commits. No new branch or worktree was created.

## Reference

The live Granola footer was inspected on October 9, 2026 at https://www.granola.ai/. It uses six layered JPEG images beneath the wordmark, with no visible playback controls. Its assets were not copied. The supplied 11.565-second recording shows a YouTube intro with orange grids and animated type; no footage or logos from that recording are used.

## Scope

Personal routes opt in through BusinessFooter's existing personal property. Both languages use the same decorative photos, and the images contain no new product claims. The original comparison on port 4511, other product lanes, provider configuration, signup behavior, and accepted checkpoint tag stay unchanged. This is a local design trial pending founder feedback, not replacement or launch approval.

## Verification

Runtime source: `7f0f1354d68ee0638ed2ebca36425b7c359af428`. Production build, typecheck, lint, and diff checks pass. All 42 focused browser checks pass across desktop and phone-sized Chromium projects. They cover both languages, a held reveal, one finite photo swap, return and replay, gentle wheel input, reduced motion, page height, and the unchanged Business pair. Existing header and footer checks also pass.

The independent scoped review found no actionable issues, added comments, or suppressions. The parent inspected the desktop first/second-photo and mobile second-photo captures, then confirmed that the in-app browser loaded the Personal sequence. Physical Safari/iPhone behavior is not claimed. The Business desktop footer screenshot is byte-identical before and after this change. Both files have SHA-256 `3e550acce9e4be97c1e16568dd5a08d43e9f06679458b9924271d61801de8098`.

- [First photo](screens/footer-es-1440-first.png) and [second photo](screens/footer-es-1440-second.png).
- [Phone reveal](screens/footer-es-390-second.png) and [resting cutoff](screens/footer-es-390-rest.png).
- [Short recording](screens/personal-footer-demo.webm), [capture manifest](screens/manifest.json), [browser results](browser-results.txt), and [build results](build-results.txt).
- [Business before](screens/business-footer-before.png) and [Business after](screens/business-footer-unchanged.png).

## Continue

Resume `codex/marketing-touchup-delivery` in the existing Marketing worktree. PR #939 remains the existing draft; these changes are local and unpushed. Preview is http://127.0.0.1:4512/personal and the separate signup mock remains on port 4513. Comparison 4511 retains its original listener. The accepted tag `codex/marketing-design-checkpoint-2026-10-09` remains at `0a026651060576a0e359efd5f2b868c70222e556`. All delegated agents have stopped and returned ownership.

After a production build, reproduce from `marketing/`:

```sh
CI=1 MARKETING_E2E_SITE_PORT=4540 MARKETING_E2E_PUBLIC_PORT=4541 MARKETING_E2E_MOCK_PORT=4542 bun run test:e2e e2e/personal-footer.spec.ts e2e/touchup.spec.ts
node scripts/capture-personal-footer.mjs
```

The capture script uses dispatched touch to hold the decorative band open and native wheel for the recorded repeat. It submits no forms. Later evidence-only commits retain these runtime bytes. No push, merge, hosted change, publication, real email or public-form activation occurred.
