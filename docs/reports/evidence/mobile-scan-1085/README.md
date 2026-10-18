# Scan capture reconciliation preparation

PR [#1085](https://github.com/lagarcess/argus/pull/1085) remains draft.
This checkpoint prepares the scan patch for review. It does not close the
physical-camera freeze or establish customer readiness.

The published starting head is `9f89918e897a625e68bd73a34c3b0abb2e12c90d`.
The fetched integration base is `5110e436e2248225ba3c68c63aa3b0280514af3b`.
The merge preserves both parents. All inherited content, including automatic
merges, was replaced with the integration tree before applying the original
eight-file scan delta from `fd2f10d6e` through `9f89918e8`.
The resulting changes are those eight files, two direct check files, and this
evidence folder. Guest PDF preparation retains integration's synchronous path.
The shared picker now encodes scan pages in the background for both callers.

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

## Open evidence

No existing offline launch fixture reaches the real authenticated connected shell
without session restoration or a synthetic HTTP server. The existing receipt
journey harness starts after acquisition and cannot prove its picker presentation.
No second UI path was added. Actual connected scanner dismissal followed by the
consent sheet remains unverified in this checkpoint.

The original physical-phone freeze cause remains unproven. A simulator has no real
document camera. Synthetic image checks do not close that gate. The Debug phone
trace remains available for the founder's next authorized physical scan.

After #1208 and #1170 land, reconcile fresh integration one way and rerun affected
checks. The root coordinator must request independent Eval at the resulting exact
head before any landing. This checkpoint does not request final Eval or authorize
merge, staging, production, TestFlight, provider calls, or paid work.
