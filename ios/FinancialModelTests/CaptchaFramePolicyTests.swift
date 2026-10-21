import Foundation
import XCTest
@testable import FinancialModels

final class CaptchaFramePolicyTests: XCTestCase {
    private let source = URL(string: "https://cuadrao-web-staging.onrender.com/auth/native-captcha")!

    func testTheWidgetsEmptyInnerFramesAreAllowedSoTheCheckCanFinish() {
        for text in ["about:blank", "about:srcdoc"] {
            XCTAssertTrue(CaptchaFramePolicy.allows(URL(string: text)!, mainFrame: false, source: source), text)
            XCTAssertFalse(CaptchaFramePolicy.allows(URL(string: text)!, mainFrame: true, source: source), "never as the page itself")
        }
        XCTAssertFalse(CaptchaFramePolicy.allows(URL(string: "about:config")!, mainFrame: false, source: source))
    }

    func testOnlyTheConfiguredPageAndCloudflareOverHTTPSLoad() {
        XCTAssertTrue(CaptchaFramePolicy.allows(source, mainFrame: true, source: source))
        XCTAssertFalse(CaptchaFramePolicy.allows(URL(string: "https://example.test/")!, mainFrame: true, source: source))
        let challenge = URL(string: "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2")!
        XCTAssertTrue(CaptchaFramePolicy.allows(challenge, mainFrame: false, source: source))
        XCTAssertFalse(CaptchaFramePolicy.allows(URL(string: "http://challenges.cloudflare.com/x")!, mainFrame: false, source: source))
        XCTAssertFalse(CaptchaFramePolicy.allows(URL(string: "https://user:pw@challenges.cloudflare.com/x")!, mainFrame: false, source: source))
        XCTAssertFalse(CaptchaFramePolicy.allows(URL(string: "https://evil.test/frame")!, mainFrame: false, source: source))
    }
}
