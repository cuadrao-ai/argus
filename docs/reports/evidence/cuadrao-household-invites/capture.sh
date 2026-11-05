#!/bin/bash
# Reruns the invitation UI tests on one simulator and copies their named screenshots into screens/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../../.." && pwd)"
: "${SIMULATOR_ID:?Set SIMULATOR_ID from: xcrun simctl list devices available}"
results="$(mktemp -d)"
RESULT_DIR="$results" "$root/ios/scripts/verify.sh" test -only-testing:ArgusFoundationUITests/InvitationsUITests
bundle="$(ls -d "$results"/test-*.xcresult | tail -1)"
xcrun xcresulttool export attachments --path "$bundle" --output-path "$results/attachments" >/dev/null
rm -rf "$here/screens" && mkdir -p "$here/screens"
python3 - "$results/attachments" "$here/screens" <<'PY'
import json, pathlib, shutil, sys
source, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
for test in json.loads((source / "manifest.json").read_text()):
    for attachment in test["attachments"]:
        name = attachment.get("suggestedHumanReadableName", "")
        if name.endswith(".png") and "_0_" in name:
            shutil.copy(source / attachment["exportedFileName"], target / (name.split("_0_")[0] + ".png"))
PY
for image in "$here"/screens/*.png; do sips -Z 1280 "$image" >/dev/null; done
ls "$here/screens"
