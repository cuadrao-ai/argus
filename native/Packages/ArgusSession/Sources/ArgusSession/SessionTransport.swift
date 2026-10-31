import Auth
import Foundation

/// Reject redirects rather than allowing password/bearer replay at a different origin.
private final class NoRedirects: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

final class SessionTransport: Sendable {
    private let fetch: AuthClient.FetchHandler
    init(fetch: @escaping AuthClient.FetchHandler) { self.fetch = fetch }
    convenience init() {
        let configuration = Self.cookieFreeConfiguration()
        let session = URLSession(configuration: configuration, delegate: NoRedirects(), delegateQueue: nil)
        self.init(fetch: { try await session.data(for: $0) })
    }
    static func cookieFreeConfiguration() -> URLSessionConfiguration {
        let config = URLSessionConfiguration.ephemeral
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        config.httpCookieAcceptPolicy = .never
        config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.timeoutIntervalForRequest = 30
        return config
    }
    func send(_ request: URLRequest, origin: URL) async throws -> (Data, HTTPURLResponse) {
        guard let url = request.url, SessionConfiguration.sameOrigin(url, origin),
              request.value(forHTTPHeaderField: "Cookie") == nil else { throw SessionFailure.invalidConfiguration }
        let (data, raw) = try await fetch(request)
        guard let response = raw as? HTTPURLResponse, let finalURL = response.url,
              SessionConfiguration.sameOrigin(finalURL, origin), !(300..<400).contains(response.statusCode)
        else { throw SessionFailure.unavailable }
        return (data, response)
    }
    func sdkFetch(origin: URL) -> AuthClient.FetchHandler {
        { [self] request in try await send(request, origin: origin) }
    }
}

final class RevokeReceipt: @unchecked Sendable {
    private let lock = NSLock()
    private var successful = false
    func observe(_ request: URLRequest, response: HTTPURLResponse) {
        guard request.url?.lastPathComponent == "logout" else { return }
        lock.lock(); defer { lock.unlock() }
        successful = (200..<300).contains(response.statusCode)
    }
    var confirmed: Bool { lock.lock(); defer { lock.unlock() }; return successful }
}
