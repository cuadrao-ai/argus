# Startup transition design working record

Founder approved this checkpoint for commit, push, and direct orchestrator handoff on 2026-10-23. Design edits stop at handoff until integration completes and ownership is explicitly returned.

Baseline: `2c22ee2853afdce65258b2b1a65b5b9619208051`, branch `codex/frontend-design-after-recovery-20261023`.

## Bug fix checklist

- [x] Reproduce it yourself on the matching surface via the driver skill. Staging authenticated reload reproduced skeleton, branded loader, Home. Password submission was not replayed.
- [x] Binary-search the cause. Independent loading presentations and per-mount delay across owner, directory, consent, and profile gates.
- [x] Plan the fix. Compare startup ownership designs, then implement with a focused failing regression.
- [ ] Verify on the same surface; the original repro now passes. Local synthetic browser proof only. Hosted verification remains an integration gate.
- [ ] Stage the commits so the failing repro lands before the fix in git history. Skip commits until requested. Preserve failing and passing logs instead.
- [ ] Run Opening a PR. Skip because this is a local design iteration with no handoff authorized.

## Design review checklist

- [x] Ground
- [x] Sketch
- [x] Agree. User approved the experience. Routine implementation decisions stay in the lane.
- [x] Implement
- [x] Scrap decision: retain the chosen boundary; its checks passed.

## Throughput checkpoint

The critical path is a stable loading owner across gate replacement. Independent work is local preview and evidence preparation. Keep provider and data logic in their current owners. Check fast entry, continuous slow entry, consent and error exits, then theme and viewport appearance.

## Architecture choice

Compare an explicit startup-stage coordinator with a presentation boundary that tracks mounted loading clients. Choose the latter. Both independent design reads agree it preserves the clock with less coupling to authentication and consent. A provider-local token set is the data shape. Clients register in layout effects; a committed empty set ends the episode. No global registry or backend stage state. The loader keeps one DOM node through pending handoffs. Terminal content releases immediately.

The Model the Domain principle shaped the idempotent token set. The business rules remain with their existing request owners.

## Local verification, 2026-10-23

- Before the fix, the new startup regression failed: the directory wait had no loading display and handoff restarted the presentation delay. Preserved red log: `temp/startup-design/loading-red.log`.
- After the fix, 25 tests pass, 0 fail, 77 assertions across business-loading, business-consent-gate, business-consent-fail-closed, business-lifecycle-directory, and business-startup-loading DOM suites. Green log: `temp/startup-design/loading-green.log`.
- Focused ESLint and `git diff --check` pass. Modularity budgets pass.
- App-source TypeScript check passes using `temp/startup-design/tsconfig.json`. It excludes test/e2e sources and the preserved, unrelated design-recovery preview. Including that old preview exposes its missing `retryCookieCleanup` fixture method. No recovery file was changed.
- Independent read-only review found no actionable issues in timer continuity, StrictMode, unmount cleanup, hidden-child accessibility, and immediate consent/error release.
- Browser replay uses the real BusinessApp and local synthetic API responses. Light and dark at desktop 1440 x 900, mobile 390 x 844 (dark), and 320 x 844 (light) are captured. Slow startup shows one loader, then Home. Consent-required and directory-error scenarios reveal their existing actionable screens.
- Fast completion below the 300 ms threshold is proven in the regression test. The browser's no-delay API scenario can still show the loader because development startup exceeds the threshold; it is not a production speed benchmark.

## Completed local viewport and accessibility pass

- Browser CSS viewports: 320 x 844, 390 x 844, and landscape 844 x 390, each in light and dark. All six cases showed a centered, unclipped loader and then Home, with no horizontal overflow at either stage. Actual DOM dimensions round down by one pixel under browser zoom.
- Each loading state exposed one localized polite status. Home replaced it and cleared that status in all six cases. Hidden startup children did not expose product controls in the loading accessibility snapshot; only local development tools remained available.
- Keyboard Tab navigation after entry reached Inicio, Bandeja, Transacciones, and Agregar with visible outlines. No hidden startup control took focus in this check. This is keyboard and DOM accessibility proof, not a spoken screen-reader audit.
- Fixed a local preview-only theme synchronization conflict so the selected theme matches the rendered iframe. Added a landscape viewport option. Neither harness change ships in the checkpoint.
- Evidence: `viewport-accessibility-verification.json`, `qa-landscape-light-loader.png`, `qa-landscape-dark-loader.png`, `qa-light-390-loader.png`, and `qa-dark-320-loader.png` in the evidence directory below.
- Production implementation was unchanged during this verification pass. The prior 25 passing tests remain the relevant test run; no full CI claim is made.

## Preview and evidence

Replay: http://127.0.0.1:4387/design-startup

Choose theme, width, language and scenario, then Replay. This starts at app entry with synthetic authentication; it does not submit real credentials. The API listens only on loopback port 4388. The harness and its symlinks are local only and must not ship.

Evidence directory: `/Users/garces/.codex/visualizations/2026/10/22/01a164fb-0899-7500-a387-b81e8f79f1a3/startup-transition-20261023/`. `review.html` shows the screenshots and links to live motion. Development controls remain visible in the captures. Browser zoom required coordinate compensation for screenshot cropping; the app viewport sizes above are iframe CSS sizes.

## Remaining verification before integration acceptance

- Repeat real sign-in and authenticated reload on the eventual integrated staging SHA. This turn changed no hosted state and submitted no real credentials.
- Native Safari, Chrome and Firefox cross-browser runs, a physical mobile device, and actual screen-reader output remain unverified in this turn.
- Reduced motion is preserved by the existing static CSS rule and reviewed in source. Runtime verification was explicitly skipped at the user's request on 2026-10-23. Do not record this as a runtime pass. No system settings were changed.
- Full CI/build and independent integration Eval remain with the future checkpoint. These local results do not certify release readiness.
- The unchanged sign-in form retains its busy state while credentials are checked. Provider/session/data behavior is unchanged by this presentation fix.

## Lane state

Approved checkpoint. Commit and push only the nine checkpoint files; exclude both local preview routes and temp harnesses. The orchestrator takes checkpoint ownership on receipt. Design stays frozen until the resulting integration SHA and explicit ownership return arrive. No deployment is authorized by this handoff.

Original design baseline: `2c22ee2853afdce65258b2b1a65b5b9619208051`. Fetched integration before handoff: `bc82cf7adb393502c51bafef90f2018d99abdcd6`. Its intervening changes do not overlap checkpoint files. Merge that baseline before the final push; report the checkpoint commit and final branch SHA in the handoff packet. Preserve approved file content through integration; material experience changes return to the founder.
