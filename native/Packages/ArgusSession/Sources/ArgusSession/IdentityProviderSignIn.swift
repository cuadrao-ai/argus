import Auth
import CryptoKit
import Foundation

/// A one-time sign-in nonce. The SHA-256 hex digest goes to Apple or Google, which
/// embed it in the ID token. The raw value goes only to Supabase Auth, which hashes it
/// and compares, so an intercepted ID token can't be replayed without the raw value.
public struct SignInNonce: Equatable, Sendable {
    public let raw: String
    public let hashed: String

    /// 32 bytes from the system CSPRNG, base64url without padding (43 characters).
    public init() {
        var generator = SystemRandomNumberGenerator()
        let bytes = (0..<32).map { _ in UInt8.random(in: .min ... .max, using: &generator) }
        self.init(raw: Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: ""))
    }

    init(raw: String) {
        self.raw = raw
        self.hashed = SHA256.hash(data: Data(raw.utf8)).map { String(format: "%02x", $0) }.joined()
    }
}

/// An ID token from a native provider sheet, ready for Supabase Auth's id_token grant.
public struct IdentityTokenCredential: Equatable, Sendable {
    public enum Provider: String, Equatable, Sendable { case apple, google }

    public let provider: Provider
    public let idToken: String
    public let nonce: SignInNonce
    /// Google only: Supabase checks the ID token's at_hash against it when present.
    public let accessToken: String?

    public init(provider: Provider, idToken: String, nonce: SignInNonce, accessToken: String? = nil) {
        self.provider = provider
        self.idToken = idToken
        self.nonce = nonce
        self.accessToken = accessToken
    }

    var wellFormed: Bool {
        // Compact JWS: three base64url segments. The server verifies everything else.
        let parts = idToken.split(separator: ".", omittingEmptySubsequences: false)
        return parts.count == 3 && parts.allSatisfy { !$0.isEmpty } && idToken.utf8.count <= 16_384
            && accessToken.map { !$0.isEmpty && $0.utf8.count <= 4_096 } != false
    }
}

/// In-memory store for the isolated id_token exchange. The issued session is handed to
/// the journaled adoption path immediately and this copy is dropped with the client.
final class ExchangeStorage: AuthLocalStorage, @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: Data] = [:]
    func store(key: String, value: Data) throws { lock.lock(); defer { lock.unlock() }; values[key] = value }
    func retrieve(key: String) throws -> Data? { lock.lock(); defer { lock.unlock() }; return values[key] }
    func remove(key: String) throws { lock.lock(); defer { lock.unlock() }; values[key] = nil }
}

public enum AppleCaptureOutcome: Equatable, Sendable {
    case saved
    case freshAuthorizationRequired
    case failed(SessionFailure)
}

public struct ProviderSignInOutcome: Equatable, Sendable {
    public let session: SessionSnapshot
    public let appleCapture: AppleCaptureOutcome?
    public let appleName: AppleNameSaveOutcome?

    init(session: SessionSnapshot, appleCapture: AppleCaptureOutcome?, appleName: AppleNameSaveOutcome? = nil) {
        self.session = session; self.appleCapture = appleCapture; self.appleName = appleName
    }
}
