# App required-reason privacy manifest

This slice adds an app-owned required-reason manifest for #800 and #831. It changes no authentication, consent, hosted feature flag, SDK, policy publication, or permission flow. The original integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.

## Audited app uses

The [source inventory](app-api-inventory.tsv) records 35 matches in app-owned Swift sources. The required API list and full approved reason definitions came from Apple's official DocC JSON on October 5, 2026. The [source ledger](source-ledger.tsv) records the dated URLs and retrieved document digest.

| Category | Declared reason | Proven use and reachability |
| --- | --- | --- |
| UserDefaults | `CA92.1` | App-local appearance and Home order preferences, Household selection, financial Search navigation, and Plan navigation. The connected launch uses these owners. Preview preferences also use app-local defaults. No app group, managed configuration, global domain, or cross-app default read appears in the inspected app source. |
| SystemBootTime | `35F9.1` | `CuadraoVoiceMessagePreview` uses `ProcessInfo.processInfo.systemUptime` to measure elapsed time between local presentation gestures. These methods remain compiled into the app. The default-off design preview can reach them. They never capture or transmit audio, boot time, or elapsed values. This declaration does not enable a voice provider or select voice launch scope. |

Apple's `CA92.1` reason permits access to app-only defaults. Its `35F9.1` reason permits elapsed-event measurements and timers, with restrictions on sending derived information. The manifest selects only these observed uses.

The receipt document picker reads `.fileSizeKey` to reject a chosen document above its size limit. That key is not in the retrieved required-reason API list. The inventory found no direct app-owned listed file-timestamp, available-disk-space, or active-keyboard API call. It does not infer a timestamp declaration from a possible framework-internal implementation. Apple's `3B52.1` describes user-authorized file metadata access, but this slice does not declare it without a listed required API use.

`NSPrivacyTracking`, tracking domains, and collected-data declarations are deliberately absent. Their audit is still open. An absent key here does not establish that the app collects no data or performs no tracking. This reason-only file is not a completed App Store privacy answer or a complete privacy compliance claim.

## Resource and verification

The target's `PBXFileSystemSynchronizedRootGroup` includes `ArgusFoundation`. Xcode packages the manifest as a resource without a project-file edit. `verify_manifest.py` compares the packaged manifest to the source and rejects missing categories, unsupported reasons, duplicate categories, and unverified tracking assertions.

Run the checks against a locally built app:

```sh
python3 docs/reports/evidence/831-required-reasons/verify_manifest.py --app /path/to/ArgusFoundation.app
```

The verification record lists the build command and actual checks. Mock provider tests and a simulator build do not prove Apple authorization, device signing, SDK signatures, or provider deletion.

## Remaining acceptance

The final device archive still needs its privacy report, dependency manifests and signatures checked at the release candidate. App Store answers, reachable permission-denial journeys, legal approval, AI disclosure, service retention, hosted settings, and phone acceptance remain open under #831 and their existing owners. This work enables no hosted feature and submits nothing to TestFlight or the App Store.

Sequence Work into Verifiable Units shaped the slice. The app resource and its packaging proof have one PR, independent of sign-in and consent runtime changes. Model the Domain kept the declaration in Apple's plist category-and-reasons structure rather than adding a runtime policy owner.
