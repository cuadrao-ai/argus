import XCTest

final class AgeSignupPayloadUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
        guard ProcessInfo.processInfo.environment["ARGUS_AGE_PAYLOAD_PROOF"] == "true" else {
            throw XCTSkip("Requires the local synthetic signup server")
        }
    }

    @MainActor
    private func assertPayload(_ response: String, adultConfirmedAt: String? = nil) async throws {
        let origin = URL(string: "http://127.0.0.1:59920")!
        let (_, reset) = try await URLSession.shared.data(from: origin.appendingPathComponent("synthetic/age-signup-reset"))
        XCTAssertEqual((reset as? HTTPURLResponse)?.statusCode, 200)
        let app = XCUIApplication()
        app.launchArguments = ["--age-confirmation-harness", "--age-response=\(response)",
                               "--age-signup-proof", "--cuadrao-guest-reset"]
        app.launch()
        defer { app.terminate() }
        XCTAssertTrue(app.staticTexts["auth.confirmation"].waitForExistence(timeout: 8))
        let (data, result) = try await URLSession.shared.data(from: origin.appendingPathComponent("synthetic/age-signup"))
        XCTAssertEqual((result as? HTTPURLResponse)?.statusCode, 200)
        let requests = try JSONDecoder().decode([[String: String]].self, from: data)
        XCTAssertEqual(requests.count, 1)
        var expected = ["email": "synthetic@example.test", "password": "synthetic-password",
                        "captcha_token": "synthetic-captcha", "language": "es-419"]
        if let adultConfirmedAt { expected["age_confirmed_at"] = adultConfirmedAt }
        XCTAssertEqual(requests.first, expected)
    }

    func testAdultObservationReachesSignupPayload() async throws {
        try await assertPayload("adult", adultConfirmedAt: "2026-01-01T00:00:00Z")
    }
    func testDeclinedObservationOmitsTimestamp() async throws { try await assertPayload("declined") }
    func testUnavailableObservationOmitsTimestamp() async throws { try await assertPayload("required-error") }
    func testUnder18ObservationOmitsTimestamp() async throws { try await assertPayload("under18") }
    func testPendingObservationDoesNotDelaySignup() async throws { try await assertPayload("pending") }
}
