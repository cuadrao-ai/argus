# Current local privacy packaging evidence

This evidence serves #831. It proves packaged declarations in an existing owned simulator app. It does not establish complete privacy compliance, actual provider retention, permission journeys, or a distribution archive.

## Retained simulator app

The [inventory](simulator-bundle-inventory.json) records the app at `/private/tmp/cuadrao-deletion-core-xcode/Build/Products/Debug-iphonesimulator/ArgusFoundation.app`. Its recorded source is `cc58b16f7f8ee4f520ffa4658f1396ba7a0cc4d7`. The existing [build and QA record](../../native-deletion-core-20261005/independent-review/README.md) owns the successful generic Debug simulator build.

All 403 recorded iOS source fingerprints match integration `8146d16e90633eb543781f8882665482f0d5dca9`. The iOS tree diff between those commits is empty. The app manifest bytes match both current source and that integration. These checks retain this native packaging evidence for 8146 without another simulator build.

The actual app contains 12 manifests, one app manifest and 11 dependency bundle manifests. Every path and SHA-256 matches the inventory committed with #849. The new inventory preserves their declarations and compiled permission purposes. It also compares pinned dependency versions with the owned cached package workspace state. The build log confirms the resolved GoogleSignIn and Supabase versions.

The app declares UserDefaults reason `CA92.1` and SystemBootTime reason `35F9.1`. Dependency declarations add UserDefaults reasons `1C8F.1` and `C56D.1`. GoogleSignIn declares linked name, email, phone number, other data, coarse location, user ID, device ID and other usage data. This is SDK-declared collection, not measured collection by the app. The app manifest omits collection and tracking keys. Omission does not prove that the app collects nothing or performs no tracking.

The compiled purpose strings cover camera, optional receipt location and saving a sample group card to Photos. No microphone or speech-recognition purpose is present. Packaging does not prove that a permission request is reachable or that denial recovery works.

The existing manifest verifier ran against this app. [Output](simulator-manifest-verification.txt) records 7 passed, 0 failed and 0 skipped. Reproduce the check with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/reports/evidence/831-required-reasons/verify_manifest.py --app /private/tmp/cuadrao-deletion-core-xcode/Build/Products/Debug-iphonesimulator/ArgusFoundation.app
```

The earlier #845 inventory remains a baseline-only SDK audit. This note adds current simulator bundle inspection. It does not relabel that older inventory as current release proof.

## One unsigned diagnostic archive attempt

The captain authorized one exclusive Mac attempt at source `f303903fdcfe8478fef33d877a2e70356c699523`. Its iOS tree also matches cc58. The attempt used Release, `iphoneos`, a generic iOS destination, cached dependencies, disabled automatic package resolution and disabled signing. It created no archive. [Sanitized result](archive-attempt.json) records exit 70 before compilation and zero tests.

`ios/Config/Development.xcconfig:12` sets `SUPPORTED_PLATFORMS = iphonesimulator`. Xcode therefore rejected the generic iOS destination. No signing input was reached. The attempt did not override the platform configuration, retry a broad build, edit source, change signing settings, launch a device or simulator, or contact a provider or hosted service.

Apple's [official report procedure](https://developer.apple.com/documentation/bundleresources/describing-data-use-in-privacy-manifests) generates the privacy report from an archive's Organizer context menu. The [official WWDC explanation](https://developer.apple.com/videos/play/wwdc2023/10060/) describes aggregation of app and linked SDK declarations into a PDF. The [dated source ledger](source-ledger.tsv) records sources inspected October 5, 2026. No purpose-built archive/privacy-report tool was exposed in this session, and `xcodebuild -help` exposed no privacy-report command. No official aggregate report was generated or substituted with this manual inventory.

Only the new owned derived-data directory was removed. The existing simulator app and shared cached dependencies were preserved. The Mac lease is terminal and released. The raw failed-build log remains local because it includes machine and device identifiers. The committed result excludes those identifiers and all signing or credential values.

## Remaining proof

The smallest local next action is a separately assigned device/archive configuration decision at its existing owner, followed by a scheduler-approved diagnostic archive and Organizer report. This evidence does not authorize changing `SUPPORTED_PLATFORMS`, signing configuration or provisioning. An unsigned diagnostic archive would still not replace distribution-signature acceptance.

Release-candidate archive inspection, SDK signature verification, App Store privacy answers, actual enabled data flows, provider retention and deletion proof, legal approval, hosted configuration and physical-phone journeys remain open. No policy was published, feature enabled, account deleted or upload performed.

Sequence Work into Verifiable Units shaped this follow-up. Existing simulator evidence was checked and recorded first. The single archive attempt then ended at its observed configuration boundary without weakening the gate.
