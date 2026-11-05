#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
chart_device="${1:?Pass the dedicated chart simulator UDID}"
chart_result="${2:-/tmp/argus-chart-ios-final-$(date +%s).xcresult}"
chart_evidence=docs/reports/evidence/chart-validation/ios
mkdir -p "$chart_evidence"
git rev-parse HEAD > "$chart_evidence/captured-head.txt"
xcodebuild -version > "$chart_evidence/toolchain.txt"
xcrun swift --version >> "$chart_evidence/toolchain.txt"
xcrun simctl list devices available | sed -n "/$chart_device/p" >> "$chart_evidence/toolchain.txt"
xcrun simctl list runtimes >> "$chart_evidence/toolchain.txt"
xcodebuild -project prototypes/chart-validation/ios/ChartPrototype.xcodeproj \
  -scheme ChartPrototype -sdk iphonesimulator -destination "id=$chart_device" \
  -derivedDataPath /tmp/argus-chart-ios -resultBundlePath "$chart_result" \
  test CODE_SIGNING_ALLOWED=NO -parallel-testing-enabled NO > "$chart_evidence/xcodebuild-test.log" 2>&1
xcrun xcresulttool get test-results summary --path "$chart_result" > "$chart_evidence/test-summary.json"
xcrun xcresulttool get test-results metrics --path "$chart_result" > "$chart_evidence/performance.json"
chart_exports="${chart_result%.xcresult}-attachments"
xcrun xcresulttool export attachments --path "$chart_result" --output-path "$chart_exports" --filter '*.png'
python3 - "$chart_exports" "$chart_evidence" <<'PY'
import json, pathlib, shutil, sys
source, destination = map(pathlib.Path, sys.argv[1:])
manifest = json.loads((source / 'manifest.json').read_text())
for test in manifest:
    for attachment in test['attachments']:
        short = attachment['suggestedHumanReadableName'].split('_0_')[0] + '.png'
        shutil.copyfile(source / attachment['exportedFileName'], destination / short)
        attachment['repositoryFile'] = short
(destination / 'attachments.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
xcrun swiftc -module-cache-path /tmp/argus-chart-model-cache \
  prototypes/chart-validation/ios/ChartPrototype/ChartData.swift \
  prototypes/chart-validation/ios/verify-model.swift -o /tmp/argus-chart-model
/tmp/argus-chart-model prototypes/chart-validation/fixtures/series.json > "$chart_evidence/model-checks.txt"
if ! xcrun simctl list devices booted | grep -q "$chart_device"; then
  xcrun simctl boot "$chart_device"
fi
xcrun simctl bootstatus "$chart_device" -b
xcrun simctl ui "$chart_device" appearance light
SIMCTL_CHILD_CHART_THEME=system SIMCTL_CHILD_CHART_CASE=stress \
  xcrun simctl launch --terminate-running-process "$chart_device" ai.argus.chartprototype
sleep 2
xcrun simctl io "$chart_device" screenshot "$chart_evidence/system-light.png"
xcrun simctl ui "$chart_device" appearance dark
sleep 2
xcrun simctl io "$chart_device" screenshot "$chart_evidence/system-dark.png"
xcrun simctl ui "$chart_device" appearance light
python3 - "$chart_evidence" <<'PY'
import hashlib, json, pathlib, subprocess, sys
files = sorted(p for p in pathlib.Path('prototypes/chart-validation/ios').rglob('*') if p.is_file() and 'xcuserdata' not in str(p))
files += [pathlib.Path('prototypes/chart-validation/fixtures') / name for name in ('series.json', 'visual-style.json')]
content = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(), 'files': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(pathlib.Path(sys.argv[1]) / 'source-identity.json').write_text(json.dumps(content, indent=2) + '\n')
PY
