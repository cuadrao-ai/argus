# Native financial-loop evidence

This is the founder-authorized local simulator deliverable for PR #745. The
founder's physical iPhone, existing identity and real data over the internet remain
the overall delivery goal; signing, installation and deployment are deferred.
The [execution manifest](../../../../specs/argus-execution-board.md) owns that status.

Native source: `d5299f65a5e9a49ccb50509b2d839107f7734f95`.
Backend source: `92020058d503459dbb7f9e2efa828dd5cddb1637`.
The evidence commit changes artifacts only. Both simulator and API used those
sources with the real local Supabase/Postgres stack and synthetic registered data.
See [sanitized results](verification.json) for exact runtime, counts and hashes.

The PR #745 review corrections are separately verified at native source
`bbfb3bffc7da1dfbd1309916a6f0847d5d51a32c` and backend
`c2425f2e2d49d8b99a39a1d52da468a109048818`. See the
[archive management acceptance](archive-review.md) for the changed native
surface. The original recording below remains evidence of its original source;
it is not presented as a new capture of the review fixes.

## Demonstration

[Connected loop recording](connected-loop.mp4) is 2 minutes 9 seconds. It starts
immediately after creating the DOP 10,000 account, then shows expense, Home,
correction, balance check, recording an expense already in the checked balance,
reopening and Spanish review. It is a continuous 12-fps capture, compressed without
cuts or speed changes. It contains synthetic app UI, no credential entry or
terminal/debug output. Initial creation and the unknown-to-known journey are
covered by XCTest and the selected screenshots, not this recording.

## Observable results

- Unknown remains unknown after an expense. Establishing a signed balance of
  DOP -25.50 asks whether the existing expense is included and survives reopening.
- DOP 10,000 becomes 8,000 after a 2,000 expense, then 7,500 after correction to
  2,500. Home is checked against its captured baseline after the write and after
  returning from the background.
- A checked balance of 7,000 retains the original -500 difference. A late expense
  of 500, excluded from opening but included in the checked balance, leaves the
  account at 7,000 and brings the unexplained difference to zero. Reopening
  preserves the account and activity; Home shows the exact corresponding delta.
- Spanish Home and balance-check review use localized controls and source copy.
- Five production-model tests cover uncertain-write replay, expired-session
  recovery, stale Home reads, owner isolation and editable placement answers.

The final connected XCTest suite passed **3/3**. The session package had **39
executed, 4 skipped, 0 failures**. Production presentation-model tests passed
**5/5**. Screenshots are visual evidence; they do not substitute for those checks.

## Selected visual evidence

- [Compact account entry](account-entry-dark.png)
- [Opening inclusion review](opening-inclusion-dark.png)
- [Connected Home](home-dark.png)
- [Balance-check review](balance-check-dark.png)
- [Reopened reconciled account](reopened-account-dark.png)
- [Spanish Home](home-spanish-dark.png)
- [Spanish balance-check review](balance-check-spanish-dark.png)

The current mobile lock and MVEE quick-setup correction are the visual references.
No forecast or unimplemented commitment values are fabricated in connected Home.

## Reproduce and resume

Connected setup and verification commands (removed; see tag `archive/ios-personal-2026-10-30`)
cover an isolated stack, existing CAPTCHA bridge, session tests, production-model
harness and the serial connected UI suite. Run the UI suite against one allocated
stack and simulator; it appends synthetic accounts and verifies Home deltas rather
than assuming an empty database. Do not reset another owner’s running stack.

For the current founder review, API 58400, CAPTCHA bridge 58405 and the retained
Supabase/Postgres stack on 58401/58402 are intentionally left running. Simulator
`197C9C31-77FD-4D31-A9C6-EACA55732B15` contains the installed app and preserved
demo session. The volume and ignored `client.json` and `verification-client.json`
remain intact. Recording/build processes and the separate archive-QA simulator
are stopped. The earlier handoff stopped local services; the captain subsequently
verified the restart recipe below and restored them without reset or reseeding.

For this preserved stack, use the core checkout below; do not configure, reset
or reseed it. Its older launcher removes inherited financial flags, so this
bounded wrapper supplies the local flag at process launch. It runs the reviewed
backend source `c2425f2e2` and does not print credentials. Skip service-start commands
while their owned ports are already listening.

```sh
cd /Users/garces/.codex/worktrees/financial-loop-core/private-alpha-next
/Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python ios/scripts/auth/local_stack.py start
/Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python - <<'PY'
import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location("local_stack", "ios/scripts/auth/local_stack.py")
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)
original_execve = os.execve

def financial_execve(path, argv, env):
    env["ARGUS_FINANCIAL_ACCOUNTS_ENABLED"] = "true"
    original_execve(path, argv, env)

os.execve = financial_execve
stack.api(sys.executable)
PY
```

If the bridge is stopped, run `python3 ios/scripts/auth/bridge.py` from the preserved
native checkout in a separate terminal. Launch the installed demo with:

```sh
xcrun simctl launch 197C9C31-77FD-4D31-A9C6-EACA55732B15 local.argus.foundation
open -a Simulator
```

Use the native fixture for UI tests and
the separate verifier fixture for HTTP checks; do not run both against the same
identity concurrently. Leave the demo services running for founder review. The
captain owns subsequent lifecycle; any later cleanup must stop only owned
processes and retain the volume and ignored fixtures.

The full local result bundle is `/tmp/argus-loop-iphone-evidence/ui-1790671670.xcresult`.
Raw bundles/logs are not committed because auth diagnostics can contain synthetic
credentials. The original selected evidence, sanitized summary and additional
archive-review correction/evidence commits are published in PR #745. The founder
authorized its existing automatic Supabase preview; all integration settings stay
unchanged. CI and scoped review completion are recorded in the PR's terminal audit.
