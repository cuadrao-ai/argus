#!/bin/bash
# Each mutation runs on a scratch copy and must make run_tap_targets.py exit 1.
set -uo pipefail
ios="$(cd "$(dirname "$0")/../../../../../ios" && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
failed=0
mutate() {
  rm -rf "$scratch/ArgusFoundation"; cp -R "$ios/ArgusFoundation" "$scratch/ArgusFoundation"
  python3 - "$scratch/ArgusFoundation/$2" "$3" "$4" <<'PY' || { echo "MUTATION NOT APPLIED: $1"; failed=1; return; }
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text(); a, b = sys.argv[2], sys.argv[3]
assert s.count(a) == 1, (a, s.count(a)); p.write_text(s.replace(a, b))
PY
  out="$(python3 "$ios/DesignPreviewTests/run_tap_targets.py" --root "$scratch/ArgusFoundation")"; code=$?
  echo "--- $1: exit $code"; echo "$out" | grep -v '^plain-style'
  [[ $code -eq 1 ]] || { echo "CHECK STAYED GREEN: $1"; failed=1; }
}
mutate "voice bar mute, shape removed" Cuadrao/CuadraoVoiceBar.swift \
  'Image(systemName: voice.muted ? "mic.slash" : "mic").frame(width: 44, height: 48).contentShape(Rectangle())' \
  'Image(systemName: voice.muted ? "mic.slash" : "mic").frame(width: 44, height: 48)'
mutate "ordered collection Edit, shape removed" Cuadrao/CuadraoOrderedCollection.swift \
  'systemImage: "pencil").frame(minHeight: 44).contentShape(Rectangle())' 'systemImage: "pencil").frame(minHeight: 44)'
mutate "voice message Cancel, shape removed" Cuadrao/CuadraoVoiceMessagePanel.swift \
  '.frame(minWidth: 80, minHeight: 48).contentShape(Rectangle())' '.frame(minWidth: 80, minHeight: 48)'
mutate "voice bar, style moved back to the container" Cuadrao/CuadraoVoiceBar.swift \
  '        }.foregroundStyle(WelcomePalette.ink)' '        }.buttonStyle(.plain).foregroundStyle(WelcomePalette.ink)'
mutate "FinancialActivityRow helper, shape removed" Accounts/AccountActivityView.swift \
  $'.padding(.vertical, 16)\n            .contentShape(Rectangle())' '.padding(.vertical, 16)'
mutate "CuadraoChoiceLabel helper, shape removed" Cuadrao/CuadraoChoiceControls.swift \
  '            .frame(minHeight: 44).contentShape(Rectangle())' '            .frame(minHeight: 44)'
rm -rf "$scratch/ArgusFoundation"; cp -R "$ios/ArgusFoundation" "$scratch/ArgusFoundation"
python3 "$ios/DesignPreviewTests/run_tap_targets.py" --root "$scratch/ArgusFoundation"; code=$?
echo "--- unmutated copy: exit $code"; [[ $code -eq 0 ]] || failed=1
exit $failed
