# Scan capture review checkpoint

PR [#1085](https://github.com/lagarcess/argus/pull/1085) is prepared for Priya's
review. This checkpoint does not close the
physical-camera freeze or establish customer readiness.

The published starting head is `9f89918e897a625e68bd73a34c3b0abb2e12c90d`.
The fetched integration base is `5110e436e2248225ba3c68c63aa3b0280514af3b`.
The merge preserves both parents. All inherited content, including automatic
merges, was replaced with the integration tree before applying the original
eight-file scan delta from `fd2f10d6e` through `9f89918e8`.
The resulting changes are those eight files, two direct check files, and this
evidence folder. Guest PDF preparation retains integration's synchronous path.
The shared picker now encodes scan pages in the background for both callers.

The final reconciliation merges integration
`f3899f4aa0d84060e0afaf270f7a983a9f8aa89c` into preparation head
`9e06eae7781ab970dffcaa12de1441e5a2be3e4c` with a normal two-parent merge.
This includes landed #1208. It has no shared files with the scan delta and does
not change capture lifecycle, data ownership, or API contracts. Its signup and
native configuration changes share app assembly, which receives a fresh build.
#1170 remains an independent lane; no unpublished #1170 work is stacked here.

## Checks on October 17, 2026

- The Debug app builds for a generic iOS Simulator with its ignored native
  configuration. No backend or web environment was read or changed.
- `ios/DesignPreviewTests/run_scan_capture.py` compiles and executes the real
  UIKit picker coordinator and file preparation code on the assigned simulator
  `8AFB6084-8918-416E-9164-E21061306BEC`.
- The checks cover asynchronous scan completion on the main thread, two-page PDF
  conversion, cancellation racing encoding, file failure, repeated completion,
  image and PDF file import, photo preparation, photo cancellation, and the
  Debug scanner stub's two camera-sized pages.
- The same runner extracts the actual connected shell's completion and dismissal
  bodies. Its logic check confirms no handoff before dismissal and one handoff
  across repeated dismissals, for scan, photo, and file input. This is logic proof.
  It does not execute the SwiftUI connected shell or establish presentation proof.
- The Release executable passes those checks and contains neither the Debug stub
  entry nor the trace file writer. See the retained Debug and Release outputs.
- The financial model suite runs 202 test methods. Four methods fail with six
  assertion failures. Integration reproduces exactly the same four failures.
  The old 164-test result is no longer the current baseline. See the retained
  comparison. The scan patch adds no model-suite failure.
- The modularity guard passes on the reconciled tree. `git diff --check` passes.

## Final integration checks

The Debug app build and Debug/Release capture checks are repeated on the
`f3899f4aa` merge result. The retained capture outputs describe this final tree.
Legal URL owner checks pass for Debug and Release. Native provider configuration
passes 11 cases in each configuration. The app's built Info.plist retains
`ARGUS_CUADRAO_LEGAL_LINKS_ENABLED=false`.

The scan and check sources are unchanged from preparation head `9e06eae77`.
The financial model source set is unchanged by #1208, so the reproduced
202-method baseline comparison remains applicable. No broad model suite is
repeated. Modularity and integration-relative whitespace checks pass again.

The social release helper requires a checkout without Local.xcconfig. It was
not run because this worktree must retain its approved native config. The
native provider checks above pass; no social settings changed in this merge.

Preparation head `9e06eae77` has only skipped draft-PR CI runs, `39084258522`
and `39084258515`. Those are not execution evidence. The PR is marked ready
after pushing the final reconciliation so full CI can start on that exact head.
The coordinator's handoff records the resulting head and CI run IDs. No commit
follows that handoff while review is pending.

## Open evidence

No existing offline launch fixture reaches the real authenticated connected shell
without session restoration or a synthetic HTTP server. The existing receipt
journey harness starts after acquisition and cannot prove its picker presentation.
No second UI path was added. Actual connected scanner dismissal followed by the
consent sheet remains unverified in this checkpoint.

The original physical-phone freeze cause remains unproven. A simulator has no real
document camera. Synthetic image checks do not close that gate. The Debug phone
trace remains available for the founder's next authorized physical scan.

Priya's independent review and terminal exact-head CI remain separate from the
local checks. Any later integration change requires an overlap check before
landing. This checkpoint does not authorize merge, staging, production,
TestFlight, provider calls, or paid work.
