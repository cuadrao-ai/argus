# Cross-platform chart evidence

Platform evidence is complete. Terminal PR review and CI are recorded in the
PR closeout comment. See the [recommendations report](../../chart-validation-prototype.md).

- [iPhone](ios/README.md): adopt Swift Charts direction; simulator limits apply.
- [Android](android/axis-precision/README.md): change dependency alignment and long-series
  performance before adoption.
- [Web](../../../../prototypes/chart-validation/web/README.md): adopt Lightweight Charts direction; WebKit touch remains
  unverified.

All data comes from the synthetic fixture bundle under
`prototypes/chart-validation/fixtures/series.json`. No market/provider request,
account, backtest, hosted change or deployment is involved.

Platform subdirectories contain their local tests, screenshots, measurements and
capture provenance. Preserve original capture heads. When an evidence-only commit
advances HEAD, record a separate source comparison rather than rewriting capture
history. Re-run any acceptance whose source changed.

## Common checks

`python3 -m unittest discover -s prototypes/chart-validation/scripts -p 'test_*.py' -v`
passes five fixture/presentation tests: dates/units/values, coverage matrix,
contribution jumps, rejection of ambiguous/invalid values, and shared series
contrast on light/dark backgrounds.

The required local mocked backend harness was attempted September 28, 2026:
237 items collected, then collection failed in
`tests/evals/test_chat_runtime_trajectory_harness.py` importing SciPy `_spropack`:
`section '__DATA/__thread_bss' has a zero-fill section type, but offset field is not zero`.
No local full-harness pass is claimed and no dependency/environment repair is
part of this chart lane. See `tests/evals/README.md` for the exact Mocked Run.

## Coordination

Existing running native-auth devices and services are occupied. Chart workers
use dedicated devices and own their cleanup. Coordination was posted to
[native-auth PR #726](https://github.com/lagarcess/argus/pull/726#issuecomment-5877685872).
No shared Docker/test resource is restarted.

## Acceptance limits

Simulated devices do not certify physical-device latency, thermal behavior,
minimum OS support, or VoiceOver/TalkBack usability. Native controls and
accessible readouts provide a testable alternative to precision dragging;
platform reports must distinguish automation from real assistive-technology use.
