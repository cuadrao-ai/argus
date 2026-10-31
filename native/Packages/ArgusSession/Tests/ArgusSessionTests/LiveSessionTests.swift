import Auth
import Foundation
import XCTest
@testable import ArgusSession

/// Opt-in, isolated local services only. This suite never runs from the ordinary
/// package command and never prints synthetic passwords or credential values.
final class LiveSessionTests: XCTestCase, @unchecked Sendable {
    func testLiveRegisteredRelaunchRevocationAndAccountSwitch() async throws {
        let fixture = try LocalSessionFixture.load()
        let client = try fixture.controller()
        do {
            let signedIn = try await fixture.login(client, user: 0)
            XCTAssertEqual(signedIn.phase, .authenticated)
            XCTAssertEqual(signedIn.profile?.id.lowercased(), fixture.users[0].id.lowercased())
            let old = try XCTUnwrap(fixture.vault.session())
            let relaunched = try fixture.controller()
            let restored = try await relaunched.restore()
            XCTAssertEqual(restored.profile, signedIn.profile)
            let signedOut = try await relaunched.signOut()
            XCTAssertEqual(signedOut.phase, .signedOut)
            let denied = try await fixture.bearerStatus(old.accessToken)
            XCTAssertEqual(denied, 401)
            let rejectedRefresh = try await fixture.refreshStatus(old.refreshToken)
            XCTAssertEqual(rejectedRefresh, 400)
            let bob = try await fixture.login(relaunched, user: 1)
            XCTAssertEqual(bob.profile?.id.lowercased(), fixture.users[1].id.lowercased())
            let cleanup = try await relaunched.signOut()
            XCTAssertEqual(cleanup.phase, .signedOut)
        } catch {
            _ = try? await client.signOut()
            throw error
        }
    }

    func testLiveConcurrentRefreshAfterExpiryMargin() async throws {
        let fixture = try LocalSessionFixture.load()
        let client = try fixture.controller()
        do {
            _ = try await fixture.login(client, user: 0)
            let before = try XCTUnwrap(fixture.vault.session())
            // Isolated stack uses a 60-second JWT. SDK refresh margin is 30 seconds.
            let wait = max(0, before.expiresAt - Date().timeIntervalSince1970 - 28)
            guard wait <= 60 else { throw XCTSkip("Local stack must use the documented short JWT expiry") }
            try await Task.sleep(for: .seconds(wait))
            let countBefore = fixture.counter.refreshCount
            let results = try await withThrowingTaskGroup(of: SessionSnapshot.self) { group in
                for _ in 0..<8 { group.addTask { try await client.profile() } }
                return try await group.reduce(into: [SessionSnapshot]()) { $0.append($1) }
            }
            XCTAssertTrue(results.allSatisfy { $0.profile?.id.lowercased() == fixture.users[0].id.lowercased() })
            XCTAssertEqual(fixture.counter.refreshCount - countBefore, 1)
            let after = try XCTUnwrap(fixture.vault.session())
            XCTAssertFalse(after.refreshToken == before.refreshToken)
            let cleanup = try await client.signOut()
            XCTAssertEqual(cleanup.phase, .signedOut)
        } catch {
            _ = try? await client.signOut()
            throw error
        }
    }

    func testLiveInvalidLoginAndConfirmationRequiredSignup() async throws {
        let fixture = try LocalSessionFixture.load()
        let client = try fixture.controller()
        do {
            _ = try await client.login(email: fixture.users[0].email, password: UUID().uuidString, captchaToken: LocalSessionFixture.captcha)
            XCTFail("Incorrect password must be rejected")
        } catch {
            guard case .rejected(status: 401, code: _) = error as? SessionFailure else {
                throw SessionFailure.invalidResponse
            }
        }
        let result = try await client.signup(email: "ios-\(UUID().uuidString.lowercased())@example.test", password: "Local-fixture-\(UUID().uuidString)", captchaToken: LocalSessionFixture.captcha, language: "es-419")
        XCTAssertEqual(result, .confirmationRequired)
        let snapshot = await client.snapshot()
        XCTAssertEqual(snapshot.phase, .signedOut)
    }
}

struct LocalSessionFixture: Sendable {
    struct User: Decodable, Sendable { let email: String; let password: String; let id: String }
    private struct Input: Decodable { let apiURL: URL; let supabaseURL: URL; let publicAnonKey: String; let users: [User] }
    // Public Cloudflare test token. Never available from the product target.
    static let captcha = "XXXX.DUMMY.TOKEN.XXXX"
    let configuration: SessionConfiguration
    let users: [User]
    let storage: DeviceKeychain
    let counter = RequestCounter()
    let transport = SessionTransport()
    var vault: CredentialVault { .init(backing: storage, prefix: configuration.storagePrefix) }

    static func load() throws -> Self {
        guard let path = ProcessInfo.processInfo.environment["ARGUS_SESSION_LIVE_CONFIG"] else {
            throw XCTSkip("Set ARGUS_SESSION_LIVE_CONFIG for the isolated local auth stack")
        }
        guard path.hasPrefix("/") else { throw SessionFailure.invalidConfiguration }
        let input = try JSONDecoder().decode(Input.self, from: Data(contentsOf: URL(fileURLWithPath: path)))
        // The existing local fixture describes an API base; product config requires
        // origins. Normalization is deliberately confined to this test harness.
        var components = try XCTUnwrap(URLComponents(url: input.apiURL, resolvingAgainstBaseURL: false))
        guard components.path == "/api/v1" || components.path.isEmpty || components.path == "/" else {
            throw SessionFailure.invalidConfiguration
        }
        components.path = ""
        let api = try XCTUnwrap(components.url)
        guard api.host == "127.0.0.1", api.port == 58400,
              input.supabaseURL.host == "127.0.0.1", input.supabaseURL.port == 58401,
              input.users.count >= 2 else { throw SessionFailure.invalidConfiguration }
        let config = try SessionConfiguration(argusAPIURL: api, supabaseURL: input.supabaseURL, publicAnonKey: input.publicAnonKey, keychainService: "argus.session.local-proof.\(UUID().uuidString)")
        return Self(configuration: config, users: input.users, storage: DeviceKeychain(service: config.keychainService))
    }
    func controller() throws -> SessionController {
        try SessionController(configuration: configuration, storage: storage, fetch: { request in
            counter.record(request)
            let origin = request.url?.host == configuration.argusAPIURL.host && request.url?.port == configuration.argusAPIURL.port ? configuration.argusAPIURL : configuration.supabaseURL
            return try await transport.send(request, origin: origin)
        })
    }
    func login(_ controller: SessionController, user: Int) async throws -> SessionSnapshot {
        try await controller.login(email: users[user].email, password: users[user].password, captchaToken: Self.captcha)
    }
    func bearerStatus(_ accessToken: String) async throws -> Int {
        var request = URLRequest(url: configuration.argusAPIURL.appending(path: "api/v1/me"))
        request.setValue("Bearer " + accessToken, forHTTPHeaderField: "Authorization")
        return try await transport.send(request, origin: configuration.argusAPIURL).1.statusCode
    }
    func refreshStatus(_ refreshToken: String) async throws -> Int {
        var request = URLRequest(url: configuration.supabaseURL.appending(path: "auth/v1/token?grant_type=refresh_token"))
        var components = URLComponents(url: configuration.supabaseURL.appending(path: "auth/v1/token"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "grant_type", value: "refresh_token")]
        request.url = components.url
        request.httpMethod = "POST"
        request.setValue(configuration.publicAnonKey, forHTTPHeaderField: "apikey")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["refresh_token": refreshToken])
        return try await transport.send(request, origin: configuration.supabaseURL).1.statusCode
    }
}

final class RequestCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var count = 0
    func record(_ request: URLRequest) {
        guard request.url?.lastPathComponent == "token" else { return }
        lock.lock(); defer { lock.unlock() }; count += 1
    }
    var refreshCount: Int { lock.lock(); defer { lock.unlock() }; return count }
}
