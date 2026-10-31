import CryptoKit
import Foundation

public struct SessionConfiguration: Sendable {
    public let argusAPIURL: URL
    public let supabaseURL: URL
    public let publicAnonKey: String
    public let keychainService: String

    /// Origins only. HTTP is limited to loopback development; no hosted settings change.
    public init(argusAPIURL: URL, supabaseURL: URL, publicAnonKey: String, keychainService: String) throws {
        guard Self.validOrigin(argusAPIURL), Self.validOrigin(supabaseURL),
              !publicAnonKey.isEmpty, !publicAnonKey.contains(where: \.isWhitespace),
              !publicAnonKey.hasPrefix("sb_secret_"), !keychainService.isEmpty
        else { throw SessionFailure.invalidConfiguration }
        let components = publicAnonKey.split(separator: ".")
        if components.count == 3 {
            var payload = String(components[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
            payload += String(repeating: "=", count: (4 - payload.count % 4) % 4)
            guard let data = Data(base64Encoded: payload),
                  let claims = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  claims["role"] as? String == "anon"
            else { throw SessionFailure.invalidConfiguration }
        } else if !publicAnonKey.hasPrefix("sb_publishable_") {
            throw SessionFailure.invalidConfiguration
        }
        self.argusAPIURL = argusAPIURL
        self.supabaseURL = supabaseURL
        self.publicAnonKey = publicAnonKey
        self.keychainService = keychainService
    }

    public var storagePrefix: String {
        let environment = Self.origin(argusAPIURL) + "|" + Self.origin(supabaseURL)
        return "argus." + SHA256.hash(data: Data(environment.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    static func origin(_ url: URL) -> String {
        "\(url.scheme?.lowercased() ?? "")://\(url.host?.lowercased() ?? ""):\(url.port ?? (url.scheme == "https" ? 443 : 80))"
    }

    static func sameOrigin(_ first: URL, _ second: URL) -> Bool {
        origin(first) == origin(second) && first.user == nil && first.password == nil
    }

    private static func validOrigin(_ url: URL) -> Bool {
        guard let host = url.host?.lowercased(), !host.isEmpty,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path.isEmpty || url.path == "/"
        else { return false }
        return url.scheme == "https" || (url.scheme == "http" && ["127.0.0.1", "localhost", "[::1]", "::1"].contains(host))
    }
}
