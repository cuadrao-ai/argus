import XCTest
@testable import ArgusSession

final class ConfigurationTests: XCTestCase {
    func testRejectsRemoteHTTPAndEmbeddedCredentials() {
        for raw in ["http://api.example.com", "https://password:secret@api.example.com", "https://api.example.com?key=x", "https://api.example.com#token", "file:///tmp/api"] {
            XCTAssertThrowsError(try configuration(api: raw), raw)
        }
    }

    func testAcceptsHTTPSAndLoopbackOrigins() throws {
        for raw in ["https://api.example.com", "http://127.0.0.1:58400", "http://localhost:58400", "http://[::1]:58400"] {
            _ = try configuration(api: raw)
        }
    }

    func testRejectsSecretRoleKeyAndEmptyConfiguration() {
        XCTAssertThrowsError(try configuration(key: ""))
        XCTAssertThrowsError(try configuration(key: "sb_secret_example"))
        let payload = Data(#"{"role":"service_role"}"#.utf8).base64EncodedString()
        XCTAssertThrowsError(try configuration(key: "header.\(payload).signature"))
    }

    private func configuration(api: String = "https://api.example.com", key: String = "sb_publishable_test") throws -> SessionConfiguration {
        try SessionConfiguration(argusAPIURL: URL(string: api)!, supabaseURL: URL(string: "https://auth.example.com")!, publicAnonKey: key, keychainService: "tests.argus")
    }
}
