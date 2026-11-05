# Mobile verification recovery, October 4, 2026

## Result and scope

The interrupted screenshot classification is complete. Codex visually inspected
all 92 differing pairs and the six new-only captures. No new layout or money-format
regression was established by these images. This is a bounded visual delta review,
not pixel equality, proof that every interaction is correct, or TestFlight acceptance.

Candidate: `03a33ef2be86cd86f4ad65c51d3e95a08a0e7ba8`.
Comparison: candidate suite attachments versus `2520da49` suite attachments.
Original capture times and test identity remain in the source manifests.
These images were captured by Claude before this takeover, not recaptured on the
report commit. This update changes documentation and evidence only.

The founder assigned the mobile lane to Codex after Claude exhausted usage.
The phone is away with the founder. No install, launch, recording, feature
activation, product-code edit or merge was performed in this recovery.

## Evidence retained and checked

The [round-two report](https://github.com/lagarcess/argus/blob/2bde54e48/docs/reports/evidence/cuadrao-iphone-candidate/reports/CANDIDATE-03a33ef2.md)
and [ledger](https://github.com/lagarcess/argus/blob/2bde54e48/docs/reports/evidence/cuadrao-iphone-candidate/LEDGER.md)
remain the source for the completed run. Codex read the raw `driver.log`:
`Executed 167 tests, with 48 tests skipped and 0 failures`, followed by
`TEST SUCCEEDED`. That means 119 passed, not 167 passed. The stopped shell shown
in the handoff screenshot did not prevent the suite from completing.

Debug/Release builds, host checks and signed build 3428 are inherited evidence
in that report. Backend, database and web evidence remains at `4af8fced`, with
the report's scope comparison. None of those suites was rerun here. The candidate
checkout was clean at the stated SHA. Build 3428 remains uninstalled; the ledger
reports profiling build 3427 on the phone. The disconnected phone was not queried.

GitHub readback at takeover: #790 `53a4d67d` has successful CI; #810
`2cd7662a` and #812 `122bb232` have no executed CI workflow checks, only a skipped
Supabase Preview. Prior independent review reports are retained. This review does
not replace missing stack CI or authorize landing. Integration remains `a8c37d3a`.

## Visual classification

The source manifest contains 273 pairs: 181 byte-identical and 92 differing.
The six additional captures are the later Group and Voice journey frames that
the older failing tests did not reach. Codex inspected those too; no new defect
was identified in the captures. The unequal split displays 500 + 300 + 400 + 400
+ 400 = 2,000. The recording/review frames retain their preview disclosure.

[classification.tsv](classification.tsv) records each of the 92 pairs by test,
name and occurrence, including the observation and disposition.
[source-hashes.tsv](source-hashes.tsv) identifies the original images. The
contact sheets below are committed visual evidence, so this report does not
rely on local paths or hashes alone. Each numbered pair is OLD on the left,
NEW on the right. They are downscaled review copies, not replacement raw captures.

- [Pairs 1–8](page-01.jpg)
- [Pairs 9–16](page-02.jpg)
- [Pairs 17–24](page-03.jpg)
- [Pairs 25–32](page-04.jpg)
- [Pairs 33–40](page-05.jpg)
- [Pairs 41–48](page-06.jpg)
- [Pairs 49–56](page-07.jpg)
- [Pairs 57–64](page-08.jpg)
- [Pairs 65–72](page-09.jpg)
- [Pairs 73–80](page-10.jpg)
- [Pairs 81–88](page-11.jpg)
- [Pairs 89–92](page-12.jpg)
- [Six new-only captures](new-only.jpg)

### Money-entry checks

Opened the larger comparison composites as well as the contact sheets for the
precision-error, valid-plan and shared-currency screenshots. Read the relevant
UI test assertions and checked the remaining composites at contact-sheet scale.
The saved run passes the money-field assertions and the subsequent save journeys.
Visible values agree: DOP 2,500.00 / 500.00; EUR 1,250,000.50 / 750.25;
USD 48,000.00 / 6,000.00 per person. The invalid precision state still shows
its error and disabled save. Large diff areas come from vertical position and
keyboard/focus state; there is no demonstrated lost digit or changed formatter.
The shared plan's create button is partly below the captured viewport; its test
explicitly scrolls to that button and then saves successfully. This is not proof
that every keyboard configuration is correct.

Larger saved comparisons:
- [Precision error](money-precision-error-es.png)
- [Valid plan](money-valid-plan-es.png)
- [Gallery money](gallery-money-dark-en.png)
- [Personal currency](currency-personal-choice-en.png)
- [Shared currency](currency-group-choice-es.png)
- [Plan creation](plan-create-es.png)

### Differences that must not be called pixel parity

- Home reorder/archive/return captures rest at different scroll offsets.
  The prior verifier measured different settling times. This recovery does not
  claim the exact cause or establish physical swipe feel from still images.
- Two Plan slider captures have different input values and therefore different
  projections. The tests use normalized gesture positions. The forecast and
  goal view files did not change between these heads. These are unsuitable as
  exact numeric visual baselines; no new calculation defect was demonstrated.
- Two chat captures lose the first-use composer hint. The unchanged
  `CuadraoChatCanvas` reads `cuadrao.design.voice-entry-learned` from AppStorage.
  Persisted state is a plausible explanation, not a proven reconstruction of
  the old simulator defaults. No hint behavior was changed to make images match.
- QR payloads, picker contents, map tiles and clock-derived expiry times are
  variable fixtures. This review checks their presentation, not real invitation
  admission, location accuracy or QR payload validity.
- Transition-frame comparisons cannot certify settled geometry. They are
  recorded separately rather than dismissed as identical screenshots.

## Foundation alignment: #814 and #815

Read #814 at `fd69c26e4129e5e1c106717fe4d707865c78dcca` and #815 at
`404a06e0a9f6cb2cb91d60f275a5f589b6e9d78f`. The master plan keeps #813 as the
mobile delivery checkpoint. These are future direction and docs alignment,
not changes incorporated into candidate `03a33ef2`.

For the next assigned mobile build, retain the locked currency separation:
Home totals per currency, primary currency first; one currency per chart;
fixed-currency plans with both actual bank amounts for cross-currency funding.
The current Home switcher and missing sample-account currency fields are
explicit gaps in #814. Do not mark them complete from the current screenshots.
The space-model change is required before TestFlight, while its model and
migration sequencing still need the stated owner decisions. Provider choices
are direction, not enabled services. Business work and archived Argus specs
are outside this verification recovery. #815 preserves compatibility pointers;
no archive or canon changes were copied into the mobile branch.

## Next acceptance, when the phone returns

1. Confirm which build is installed and whether the profiling checkpoint can
   be replaced, then install the saved candidate if appropriate. Keep the prior
   profiling evidence; do not overwrite it with an unlabeled run.
2. Check Home scroll/reorder, period paging, sheet presentation/dismissal,
   keyboard entry and tabs on the phone, preserving the approved interactions.
3. Run connected sign-in/invite/Household and financial persistence journeys
   only against the authorized configured service. Build 3428 has auth and
   invitation flags off; installing that preview alone cannot prove these paths.
4. Keep #784, #800, #805, #806, #778 and #811 acceptance open as applicable.
   No hosted enablement, migration, provider call or security fix was performed.

Mac work remains serialized under the existing simulator/device lock. No full
suite rerun is needed merely to classify existing attachments. Future behavioral
changes require their affected checks. The broader onboarding, agentic-runtime,
privacy and foundation work stays in the execution board and #814.
