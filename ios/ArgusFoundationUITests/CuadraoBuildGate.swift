import XCTest

/// The bundle's principal class (`NSPrincipalClass` in this target's Info.plist), so it observes
/// every test whichever runner started the bundle. Without `ARGUS_AUTH_ENABLED = true` the app
/// under test builds as the legacy foundation preview, and no result against it may count.
///
/// Suites that run auth-disabled on purpose (the offline design pass and the legacy shell tests)
/// set `ARGUS_UI_TESTS_ALLOW_PREVIEW_BUILD=true` in the runner environment, which `xcodebuild`
/// forwards from `TEST_RUNNER_ARGUS_UI_TESTS_ALLOW_PREVIEW_BUILD`. Unset, the gate stays strict.
@objc(CuadraoBuildGate)
final class CuadraoBuildGate: NSObject, XCTestObservation {
    private static let previewOptOutKey = "ARGUS_UI_TESTS_ALLOW_PREVIEW_BUILD"
    private let previewBuildAllowed =
        ProcessInfo.processInfo.environment[CuadraoBuildGate.previewOptOutKey] == "true"
    private var missingConfiguration: String?

    override init() {
        super.init()
        XCTestObservationCenter.shared.addTestObserver(self)
    }

    func testBundleWillStart(_ testBundle: Bundle) {
        guard !previewBuildAllowed else { return }
        let auth = testBundle.object(forInfoDictionaryKey: "ARGUS_AUTH_ENABLED") as? String ?? ""
        guard auth != "true" else { return }
        missingConfiguration = """
            CUADRAO UI TESTS STOPPED: ios/Config/Local.xcconfig is missing or does not set \
            ARGUS_AUTH_ENABLED = true (this build has "\(auth)"), so the app under test is the legacy \
            foundation preview, not Cuadrao. Create the ignored ios/Config/Local.xcconfig, then build for \
            testing again: `python3 ios/scripts/auth/local_stack.py seed` writes it for the local stack \
            (ios/AUTH_SETUP.md, Local acceptance), or `cp ios/Config/Local.xcconfig.example \
            ios/Config/Local.xcconfig` and set ARGUS_AUTH_ENABLED = true with the loopback URLs.
            A deliberate offline or preview run sets TEST_RUNNER_ARGUS_UI_TESTS_ALLOW_PREVIEW_BUILD=true.
            """
    }

    func testCaseWillStart(_ testCase: XCTestCase) {
        if let missingConfiguration {
            // Recorded before setUp with continueAfterFailure off, it ends the test before any app step.
            testCase.continueAfterFailure = false
            testCase.record(XCTIssue(type: .system, compactDescription: missingConfiguration,
                                     sourceCodeContext: XCTSourceCodeContext(location: XCTSourceCodeLocation(
                                        filePath: #filePath, lineNumber: #line))))
            return
        }
        guard !previewBuildAllowed else { return }
        // Second line: an app and a test bundle from different builds can still reach the legacy preview.
        // Journeys end on many Cuadrao screens, so only the legacy marker is a sound per-test check.
        testCase.addTeardownBlock {
            let app = XCUIApplication()
            guard app.state == .runningForeground, app.staticTexts["sample.notice"].exists else { return }
            XCTFail("CUADRAO UI TESTS: this test ran against the legacy foundation preview, not Cuadrao, "
                + "whose first screen is the welcome lockup cuadrao.welcome.lockup (DESIGN.md section 13). "
                + "Build the app and the UI tests together with ios/Config/Local.xcconfig present.")
        }
    }
}
