#!/bin/bash
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
action="${1:-test}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ "$action" != build && "$action" != test ]]; then
  echo "Usage: SIMULATOR_ID=<UDID> $0 [build|test]" >&2
  exit 2
fi
if [[ -z "${SIMULATOR_ID:-}" ]]; then
  echo "Set SIMULATOR_ID from: xcrun simctl list devices available" >&2
  exit 2
fi
python3 "$ios_dir/scripts/check-age-sdk.py"
python3 "$ios_dir/scripts/localization_guard.py"
result_dir="${RESULT_DIR:-$ios_dir/.build/results}"
mkdir -p "$result_dir"
result_bundle="$result_dir/$action-$(date -u +%Y%m%dT%H%M%SZ).xcresult"
xcodebuild "$action" \
  -project "$ios_dir/ArgusFoundation.xcodeproj" \
  -scheme ArgusFoundation -configuration Debug \
  -destination "platform=iOS Simulator,id=$SIMULATOR_ID" \
  -derivedDataPath "$ios_dir/.build/DerivedData" \
  -resultBundlePath "$result_bundle" \
  -parallel-testing-enabled NO \
  CODE_SIGNING_REQUIRED=NO \
  "$@" 2>&1 | tee "${result_bundle%.xcresult}.log"
