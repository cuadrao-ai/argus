#!/bin/bash
# Mac pass for the Cuadrao design graft (#783, #785, #786 and PR 4 of 4).
# Checklist, expected differences and sign-off: docs/reports/evidence/784/README.md.
#
#   SIMULATOR_ID=<iPhone UDID> ios/scripts/cuadrao-design-mac-pass.sh [all|checks|tests|screens]
#
# checks   DesignPreviewTests state checks (xcrun swiftc, no simulator).
# tests    The design UI tests plus CuadraoHomeChartUITests, then their screenshot attachments.
# screens  Before/after launch screenshots: BASELINE (default 2185aefe) against this tree,
#          for a default launch and a --cuadrao-design launch, in light and dark.
#
# Output goes to ios/.build/mac-pass/<UTC stamp>/ (ignored by git). Nothing here signs,
# uploads or calls a backend; the default launch stays signed out.
#
# A failing step doesn't stop the later ones: `all` always runs checks, tests and screens,
# then exits non-zero if any of them failed.
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$ios_dir/.." && pwd)"
step="${1:-all}"
baseline="${BASELINE:-2185aefe}"
settle="${SETTLE_SECONDS:-4}"
if [[ "$step" != all && "$step" != checks && "$step" != tests && "$step" != screens ]]; then
  echo "Usage: SIMULATOR_ID=<UDID> $0 [all|checks|tests|screens]" >&2
  exit 2
fi
if [[ "$step" != checks && -z "${SIMULATOR_ID:-}" ]]; then
  echo "Set SIMULATOR_ID from: xcrun simctl list devices available" >&2
  exit 2
fi
out="${OUT_DIR:-$ios_dir/.build/mac-pass/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$out"
echo "Mac pass output: $out"

design_tests=(
  CuadraoHomeChartUITests
  CuadraoCollectionUITests CuadraoConsistencyUITests CuadraoContextUITests
  CuadraoGroupDesignUITests CuadraoHistoryDesignUITests CuadraoPlanCurrencyUITests
  CuadraoPlanDesignUITests CuadraoPolishUITests CuadraoProfileFollowupUITests
  CuadraoReceiptPermissionUITests CuadraoReceiptUITests CuadraoSignInPresentationUITests
  CuadraoSupportUITests CuadraoVoiceDesignUITests ReleaseUIJourneyTests
)

# Each runner is non-fatal so one broken check can't hide the others, the tests or the screens.
run_checks() {
  local runner failed=0
  {
    for runner in run_home_balance run_plan_preview run_group_preview run_receipt_preview \
                  run_temporary_chat run_avatar_crop run_release_updates run_release_identity run_tap_targets \
                  run_money_format run_cuadrao_legal_urls; do
      echo "== $runner"
      python3 "$ios_dir/DesignPreviewTests/$runner.py" || { echo "FAILED $runner"; failed=1; }
    done
  } 2>&1 | tee "$out/design-preview-checks.log"
  [[ "${PIPESTATUS[0]}" -eq 0 ]] || failed=1
  grep -q '^FAILED ' "$out/design-preview-checks.log" && failed=1
  return "$failed"
}

run_tests() {
  local only=() name status=0 bundle
  for name in "${design_tests[@]}"; do only+=("-only-testing:ArgusFoundationUITests/$name"); done
  # These design classes run auth-disabled and offline on purpose; the opt-out lets the UI test
  # build gate (CuadraoBuildGate) pass them. Without it every test stops on the missing Local.xcconfig.
  TEST_RUNNER_ARGUS_UI_TESTS_ALLOW_PREVIEW_BUILD=true RESULT_DIR="$out/results" \
    "$ios_dir/scripts/verify.sh" test "${only[@]}" || status=$?
  bundle="$(ls -dt "$out"/results/*.xcresult 2>/dev/null | head -1 || true)"
  if [[ -n "$bundle" ]]; then
    xcrun xcresulttool export attachments --path "$bundle" --output-path "$out/ui-attachments" \
      || echo "Could not export attachments; open $bundle in Xcode instead."
  fi
  # Connected sign-in exists only with auth on; loopback placeholders keep it offline and signed out,
  # and the command line forces both social flags off over any local override.
  TEST_RUNNER_ARGUS_TEST_AUTH_UI_ENABLED=true RESULT_DIR="$out/results-auth" "$ios_dir/scripts/verify.sh" test \
    -only-testing:ArgusFoundationUITests/CuadraoSignInPresentationUITests/testDefaultLaunchOffersNoAppleSignIn \
    ARGUS_AUTH_ENABLED=true ARGUS_API_URL=http://127.0.0.1:9 ARGUS_SUPABASE_URL=http://127.0.0.1:9 \
    ARGUS_SUPABASE_ANON_KEY=sb_publishable_mac_pass_placeholder ARGUS_WEB_URL=http://127.0.0.1:9 \
    ARGUS_CAPTCHA_URL=http://127.0.0.1:9/captcha \
    ARGUS_APPLE_SIGN_IN_ENABLED=false ARGUS_GOOGLE_SIGN_IN_ENABLED=false || status=$?
  return "$status"
}

prepare_simulator() {
  xcrun simctl boot "$SIMULATOR_ID" 2>/dev/null || true
  xcrun simctl bootstatus "$SIMULATOR_ID" -b >/dev/null
  xcrun simctl status_bar "$SIMULATOR_ID" override --time 9:41 --batteryState charged \
    --batteryLevel 100 --cellularBars 4 --wifiBars 3
}

# build_app <ios dir> <derived data dir>: prints the built .app path. Both builds pin the
# flags on the command line: the baseline worktree has no ignored ios/Config/Local.xcconfig,
# so this tree's local overrides must not apply to one side only.
build_app() {
  xcodebuild build -project "$1/ArgusFoundation.xcodeproj" -scheme ArgusFoundation \
    -configuration Debug -destination "platform=iOS Simulator,id=$SIMULATOR_ID" \
    -derivedDataPath "$2" CODE_SIGNING_REQUIRED=NO \
    ARGUS_AUTH_ENABLED=false CUADRAO_DESIGN_PREVIEW=false >"$2.log" 2>&1 || return 1
  find "$2/Build/Products/Debug-iphonesimulator" -maxdepth 1 -name '*.app' ! -name '*-Runner.app' | head -1
}

# install_app <.app>: clean install so no preview or appearance state carries over.
install_app() {
  bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Info.plist")"
  xcrun simctl uninstall "$SIMULATOR_ID" "$bundle_id" >/dev/null 2>&1 || true
  xcrun simctl install "$SIMULATOR_ID" "$1"
}

# shoot <name> <light|dark> [launch arguments...]
shoot() {
  local name="$1" look="$2"; shift 2
  xcrun simctl terminate "$SIMULATOR_ID" "$bundle_id" >/dev/null 2>&1 || true
  xcrun simctl ui "$SIMULATOR_ID" appearance "$look"
  xcrun simctl launch "$SIMULATOR_ID" "$bundle_id" "$@" >/dev/null
  sleep "$settle"
  xcrun simctl io "$SIMULATOR_ID" screenshot "$out/screens/$name.png" >/dev/null
  echo "  $name.png"
}

# The two launches compared before/after, in both appearances.
shoot_common() {
  local tag="$1" look
  for look in light dark; do
    shoot "$tag-default-$look" "$look"
    shoot "$tag-design-$look" "$look" --cuadrao-design -cuadrao.design.appearance "$look"
  done
}

run_screens() {
  local app look
  work="$(mktemp -d)/baseline-src"
  mkdir -p "$out/screens"
  prepare_simulator
  echo "== baseline $baseline"
  git -C "$repo_dir" worktree add --detach "$work" "$baseline" >/dev/null
  trap 'git -C "$repo_dir" worktree remove --force "$work" 2>/dev/null || true' EXIT
  app="$(build_app "$work/ios" "$out/baseline-build")"
  install_app "$app"
  shoot_common before
  git -C "$repo_dir" worktree remove --force "$work"; trap - EXIT
  echo "== this tree ($(git -C "$repo_dir" rev-parse --short HEAD))"
  app="$(build_app "$ios_dir" "$out/head-build")"
  install_app "$app"
  shoot_common after
  for look in light dark; do
    shoot "after-design-home-$look" "$look" --cuadrao-design --cuadrao-home --home-populated \
      -cuadrao.design.appearance "$look"
    shoot "after-design-gallery-$look" "$look" --cuadrao-design --design-gallery \
      -cuadrao.design.appearance "$look"
  done
  compare_pairs | tee "$out/screens/compare.txt"
}

compare_pairs() {
  local pair before after
  for pair in default-light default-dark design-light design-dark; do
    before="$out/screens/before-$pair.png"; after="$out/screens/after-$pair.png"
    if command -v compare >/dev/null; then
      printf '%s: %s differing pixels\n' "$pair" \
        "$(compare -metric AE "$before" "$after" "$out/screens/diff-$pair.png" 2>&1 || true)"
    elif cmp -s "$before" "$after"; then
      echo "$pair: identical files"
    else
      echo "$pair: files differ; compare by eye (install ImageMagick for a pixel count)"
    fi
  done
}

status=0
failed_steps=()
# run_step <name> <function>: runs the step in a subshell with errexit still on (an `if` or
# `||` would switch it off inside the function), records a failure and carries on.
run_step() {
  local name="$1" rc; shift
  set +e
  ( set -e; "$@" )
  rc=$?
  set -e
  if (( rc == 0 )); then
    echo "== $name: ok"
  else
    echo "== $name: FAILED (exit $rc)"
    failed_steps+=("$name"); status=1
  fi
}
case "$step" in
  checks) run_step checks run_checks ;;
  tests) run_step tests run_tests ;;
  screens) run_step screens run_screens ;;
  all) run_step checks run_checks; run_step tests run_tests; run_step screens run_screens ;;
esac
echo "Mac pass output: $out"
if (( status != 0 )); then echo "Failed steps: ${failed_steps[*]}"; fi
exit "$status"
