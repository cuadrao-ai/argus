# Cross-platform chart validation

Rendering and interaction prototype, September 28, 2026. Synthetic data only.
Recommendations concern library direction only. Terminal PR review/CI and the
exact deliverable head are recorded in the PR closeout comment after review.

## Scope and contract

The [spec](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-09-28-chart-validation-prototype.md) bounds
the work. [Prototype setup](../../prototypes/chart-validation/README.md) links
standalone platform commands. One [proposed fixture contract](../../prototypes/chart-validation/CONTRACT.md)
preserves canonical historical `{time, value}` semantics and adds prototype-only
projection and gap columns. Clients neither infer financial facts nor fetch data.

Each platform displays the same six fixture cases, including recurring
contributions and 2,000 points. Negative amounts are renderer stress cases, not
claimed long-only portfolio outcomes. Gaps remain missing; contribution jumps
are nominal cash changes, not returns. Civil dates display in UTC independently
of device timezone. Locale formatting may differ slightly with platform ICU.

## Reference and toolchain disposition

All references were inspected as OPEN/unmerged:

| Reference | Inspected head | Reuse |
| --- | --- | --- |
| #727 | `802b82306cc29373d7e4dce44c17d33adb243e30` | Approved chart direction and design constraints |
| #729 | `b422d986bcf068b56e07283481de373ba8e30dc0` | Simulator-only Xcode setup and iOS 17 configured floor |
| #730 | `edc43cb7961b68e7ca699a4101510a79667d1a7f` | AGP 9.1.1 / Gradle 9.3.1 / Compose 2.2.10 setup; API 26 configured floor |

These were inspected references, not assumed merged dependencies. #727 later
landed in integration; #729 and #730 subsequently landed too. All were reconciled as
described below. No foundation shell or shared
build configuration changes. Installed Xcode is 27.0 (27A266a). Web retains the
repository's Lightweight Charts 5.2.0. Platform reports own verified dependency
versions, official documentation citations and compatibility limitations.

## Evidence and recommendations

See [durable evidence](evidence/chart-validation/README.md) and the
[bounded visual acceptance audit](evidence/chart-validation/visual-acceptance.md).

| Platform | Recommendation | Proof and limitations |
| --- | --- | --- |
| iPhone / Swift Charts | **Adopt direction** | Build, eight UI tests, fixture model checks, thirteen screenshots plus motion recording on iPhone 17e / iOS 26.5. iOS 17 minimum runtime, physical devices and full VoiceOver remain unverified; hitch samples unavailable. |
| Android / Vico 2.5.1 | **Change before adoption** | Build, lint, three unit tests and eight emulator tests pass; twenty revised screenshots plus motion recording. The app-only long-series sample has substantial jank. Isolated resolution raises Compose UI/runtime/foundation to 1.11.1, Material3 to 1.4.0, core-ktx to 1.18.0 and Kotlin stdlib to 2.3.21 while the Compose compiler plugin remains 2.2.10. Coordinate this convergence with the Android foundation owner before any shared build/product integration. API 26 and physical TalkBack/performance remain unverified. |
| Web / Lightweight Charts 5.2.0 | **Adopt direction** | Three model tests plus Chromium 147 and WebKit 26.4 browser suites, sixteen screenshots plus touch recording. Chromium real browser touch events prove cancel/release/vertical scrolling. WebKit touch gestures, physical devices and screen-reader use remain unverified. |

Each recommendation retains explicit segment splitting, accessible point controls
and selection lifecycle. No library's default behavior alone supplies these facts.
Native charts use elapsed civil-date spacing; Lightweight Charts uses sample-index
spacing (explicit missing rows retain a position). Readouts always use the same
authored date/value. Neither spacing choice invents intermediate observations.

Measured performance, on the shared arm64 Mac rather than physical phones:

- iPhone simulator: five 2,000-point scrubs average 1.169 seconds including touch
  injection/XCTest, 0.976 seconds application CPU, 47,345 kB peak memory. No frame
  rate or zero-hitch claim follows from missing hitch samples.
- Web: 2,000-point construction through two animation callbacks takes 17.3–22 ms
  in Chromium and 33–51 ms in WebKit. Readout formatting/DOM p95 is 0.4/1 ms.
  These exclude input delivery and GPU completion; idle frame timing is not FPS.
- Android: the app-only 2,000-point sample records 99 frames, 100% jank and
  frame p95 101 ms; the instrumented sample records 36 frames, 33.33% jank and
  p95 65 ms. Both are retained. SwiftShader software rendering and a debug APK
  limit transfer to physical devices. Improve and remeasure before adoption.

These different instruments are not a cross-platform speed ranking or a production
SLO. Screenshots and tests prove rendering/interaction, not engine correctness.
Local mocked backend collection is blocked by the existing SciPy `_spropack`
loader failure, independently of these standalone clients. No full local backend
pass is claimed.

## Integration and review

Original fetched branch: `origin/codex/private-alpha-next`.
Original full integration SHA: `4b84e054a0d8079b21f38784335ad3241809b4cd`.
Worker: `codex/chart-validation-prototype` in isolated worktree `2825`.
Spec-first commit: `f1304516`.

Integration advanced to `4e024a4e2837058e73c4be6c528fc41f24d7a03e` with #728's
server Supabase Auth session isolation fix. It changes the server gateway,
guest-account helper, auth tests and its evidence only. This prototype has no
auth/network/runtime/persistence dependency, shared UI state, migration or
environment-variable owner, so there is no semantic overlap. A one-way merge
retains chart evidence; no provider or auth rerun is justified. Merged-tree
modularity passes. Merge commit: `e3752dbe938d2fd7638b655fa2811dba3ef4fe4e`.

A subsequent fetch found `25015963600fa9dd9290080bf641238693509a37` (#695): Render
hostname configuration, release docs and internet benchmark/test changes. There
is no shared chart runtime, API/data contract, UI state, migration, local native
environment variable or directly affected chart test. Merge commit:
`f93e11d7e639b77b5ffd82ec9d04076bdb6dd713`. Chart acceptance is retained by explicit
source/fixture equality, not merely the absence of Git conflicts.

Integration then advanced to `3fa0dd92167791d82ce81c167c490396358c4316` with
#727's design publication. This has semantic overlap in design authority, so its
DESIGN/ARCHITECTURE changes were audited against the prototype refinement. Those
two files are byte-identical to inspected `origin/reference-727`; the refined
palette, fonts, quiet controls and accessible hit areas follow that direction.
No runtime, API/data, migration or native build owner changed. One-way merge:
`b6aecdfdaf964f81aeb411110c003d9662bd5e68`. Final visual captures cover the affected
presentation; original pre-refinement screenshots are superseded, not reused.

The next fetch found `f61e47f1243d94fe5d5fa631c4bd9f67906fcfc9`: #713's
integration landing report and #729's iPhone foundation. The latter is a separate
Xcode project/app and does not own this prototype's resource bundle, selection
state, API/data contract or build configuration. Fonts previously inspected from
#729 remain unchanged in the prototype. No runtime/test or environment-variable
overlap invalidates its captured behavior. One-way merge:
`41c2b77da708e3c2e668c03d060aba4a566f9f3b`. Relevant prototype/style/fixture/font/
web-lockfile diffs are empty; final source hashes and merged-tree modularity were
revalidated. CI runs against this reconciled lineage.

The final native foundation landing advanced integration to
`a8e09b72339c7bc676715dabf8a9cceaac81cf03` (#730). One-way merge:
`dd59bde8b1c458a6f8bf061d61d11addb25ba425`. Its `mobile/android/` app, Gradle
project, navigation state and path-filtered foundation workflow are separate from
this prototype. AGP/Compose compiler/Gradle versions and font assets match the
inspected reference. The Vico dependency uplift remains a separate adoption
condition. No chart sources, shared fixtures, presentation tokens, web fonts or
lockfile changed; preserve visual/performance evidence and the reviewed worker
source delta. Run normal final-head CI and merged-tree modularity again.

A later fetch found only #734's #695 landing report at
`acf6639a23be368dbf3848a2b873f4a69d7579c4`; merged one way as
`62c6e674cb16576c25f71e90377826d3ac21b3e8`. This changes documentation only, with
no prototype runtime, contract, state, migration, environment or test overlap.
The Android review then identified rounded fractional scale labels. One numeric
presentation policy now serves axis/readout values, with exact decimal midpoint
geometry. Its affected Android evidence is refreshed in `android/axis-precision/`;
unchanged iPhone/web sources and captured evidence remain valid.

The next fetch found #672 at `86df1ee95cc3c88d713efa6a24538c6217b2ea29`.
Its documentation clarifies shipped memory/sharing and the calculation registry,
adds historical release evidence, and explicitly preserves this chart lane's
isolated ownership. The voice/chart direction and DESIGN are unchanged. There is
no chart runtime, API/data contract, UI state, migration, environment or test
owner overlap. One-way merge: `83d63d81a639609757d27fcdde52d7720b3d3bdd`.
Source/hash equality retains final platform evidence and the scoped precision
review; final merged-tree checks and CI run again.

The initial captures were superseded where the visual refinement changed sources.
Platform provenance identifies the final capture heads; original source identities
remain in Git history. Android uses the explicit-install test runner.
Evidence history keeps original capture heads; the final revalidation record
compares tested files to the final PR source. The local latest-delta review is
clean. GitHub review/CI remains a separate terminal gate recorded in closeout.

## Cleanup

Native-auth coordination is linked in the evidence index. Existing devices,
Docker, auth stack and shared services remain untouched. Platform reports record
owned device/server IDs and their terminal disposition. Worktree and branch stay
available for the founder's PR review. iPhone simulator
`AAC78F82-61C2-4E51-A14C-4F341CD19A79` is shut down; browser sessions and the owned
4179 server are stopped. Android's own `emulator-5584` and isolated Gradle daemon
are stopped, and its app/test packages are uninstalled. Disposable `/tmp`
build/result caches and the stopped dedicated devices remain reusable; they are
not the durable evidence store.
All bounded workers finish after evidence/cleanup; no continuing agent assignment.
No merge or deployment is authorized.
