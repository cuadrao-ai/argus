import SwiftUI
import WebKit

/// Only the configured main document may return a token. Each presentation owns
/// a fresh, nonpersistent web view and completes at most once.
struct CaptchaChallengeView: View {
    let sourceURL: URL
    let completion: (Result<String, CaptchaFailure>) -> Void
    @State private var completed = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            CaptchaWebView(sourceURL: sourceURL, completion: finish)
                .navigationTitle("auth.captcha.title")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    CuadraoCancelToolbar(title: "auth.cancel", identifier: "auth.captcha.cancel") { finish(.failure(.cancelled)) }
                }
                .task {
                    do {
                        try await Task.sleep(for: .seconds(90))
                        finish(.failure(.unavailable))
                    } catch { }
                }
        }
        .interactiveDismissDisabled()
        .accessibilityIdentifier("auth.captcha")
    }

    private func finish(_ result: Result<String, CaptchaFailure>) {
        guard !completed else { return }
        completed = true
        completion(result)
        dismiss()
    }
}

enum CaptchaFailure: Error { case cancelled, unavailable }

private struct CaptchaWebView: UIViewRepresentable {
    let sourceURL: URL
    let completion: (Result<String, CaptchaFailure>) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(sourceURL: sourceURL, completion: completion) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController.add(context.coordinator, name: "argusCaptcha")
        #if DEBUG
        CaptchaConsoleLog.attach(to: configuration.userContentController)
        #endif
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.load(URLRequest(url: sourceURL, cachePolicy: .reloadIgnoringLocalCacheData))
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) { }

    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        coordinator.completed = true
        view.stopLoading()
        view.navigationDelegate = nil
        view.configuration.userContentController.removeScriptMessageHandler(forName: "argusCaptcha")
    }

    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
        let sourceURL: URL
        let completion: (Result<String, CaptchaFailure>) -> Void
        var completed = false

        init(sourceURL: URL, completion: @escaping (Result<String, CaptchaFailure>) -> Void) {
            self.sourceURL = sourceURL
            self.completion = completion
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard !completed,
                  message.name == "argusCaptcha", message.frameInfo.isMainFrame,
                  message.frameInfo.request.url == sourceURL, message.webView?.url == sourceURL,
                  message.frameInfo.securityOrigin.protocol == sourceURL.scheme,
                  message.frameInfo.securityOrigin.host == sourceURL.host,
                  normalizedPort(message.frameInfo.securityOrigin.port) == (sourceURL.port ?? (sourceURL.scheme == "https" ? 443 : 80)),
                  let body = message.body as? [String: Any], let type = body["type"] as? String else {
                finish(.failure(.unavailable)); return
            }
            if type == "token", Set(body.keys) == ["type", "token"],
               let token = body["token"] as? String, !token.isEmpty,
               token.utf8.count <= 4096,
               token.unicodeScalars.allSatisfy({ !CharacterSet.whitespacesAndNewlines.contains($0) && !CharacterSet.controlCharacters.contains($0) }) {
                finish(.success(token))
            } else {
                finish(.failure(.unavailable))
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let target = navigationAction.targetFrame, let url = navigationAction.request.url else {
                decisionHandler(.cancel); finish(.failure(.unavailable)); return
            }
            let allowed = CaptchaFramePolicy.allows(url, mainFrame: target.isMainFrame, source: sourceURL)
            #if DEBUG
            if !allowed { CaptchaConsoleLog.write("blocked frame " + (url.scheme == "about" ? url.absoluteString : (url.scheme ?? "") + "://" + (url.host ?? "") + url.path)) }
            #endif
            decisionHandler(allowed ? .allow : .cancel)
            if target.isMainFrame && !allowed { finish(.failure(.unavailable)) }
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                     decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            if navigationResponse.isForMainFrame,
               (navigationResponse.response.url != sourceURL || (navigationResponse.response as? HTTPURLResponse)?.statusCode != 200) {
                decisionHandler(.cancel); finish(.failure(.unavailable))
            } else { decisionHandler(.allow) }
        }

        func webView(_ webView: WKWebView, didReceiveServerRedirectForProvisionalNavigation navigation: WKNavigation!) {
            if webView.url != sourceURL {
                webView.stopLoading()
                finish(.failure(.unavailable))
            }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            finish(.failure(.unavailable))
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            finish(.failure(.unavailable))
        }
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { finish(.failure(.unavailable)) }

        private func normalizedPort(_ port: Int) -> Int {
            port == 0 ? (sourceURL.scheme == "https" ? 443 : 80) : port
        }

        private func finish(_ result: Result<String, CaptchaFailure>) {
            guard !completed else { return }
            completed = true
            completion(result)
        }
    }
}

#if DEBUG
import os

/// Debug only (`--captcha-console`): copies the CAPTCHA page's console warnings and errors, and frames the view
/// refuses, to the app log, so a failed check shows its provider code. Tokens are never logged.
enum CaptchaConsoleLog {
    static var enabled: Bool { ProcessInfo.processInfo.arguments.contains("--captcha-console") }
    private static let log = Logger(subsystem: "local.argus.captcha", category: "console")

    static func write(_ text: String) {
        guard enabled else { return }
        log.notice("[captcha-console] \(text, privacy: .public)")
    }

    static func attach(to controller: WKUserContentController) {
        guard enabled else { return }
        let script = """
        (function () {
          var post = function (kind, args) {
            try {
              var text = Array.prototype.map.call(args, function (a) { return String(a); }).join(" ");
              window.webkit.messageHandlers.argusCaptchaConsole.postMessage(kind + ": " + text.slice(0, 300));
            } catch (e) {}
          };
          ["warn", "error"].forEach(function (kind) {
            var original = console[kind];
            console[kind] = function () { post(kind, arguments); return original.apply(console, arguments); };
          });
          window.addEventListener("error", function (event) { post("window.error", [event.message, event.filename || ""]); }, true);
          window.addEventListener("unhandledrejection", function (event) { post("rejection", [event.reason]); });
        })();
        """
        controller.addUserScript(WKUserScript(source: script, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        controller.add(Handler(), name: "argusCaptchaConsole")
    }

    private final class Handler: NSObject, WKScriptMessageHandler {
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            CaptchaConsoleLog.write((message.body as? String) ?? "")
        }
    }
}

/// `--captcha-harness`: opens the configured CAPTCHA page alone, with no sign-in, and shows only whether a token came back.
struct CaptchaHarness: View {
    @State private var presenting = false
    @State private var result = "idle"
    private var url: URL? { (Bundle.main.object(forInfoDictionaryKey: "ARGUS_CAPTCHA_URL") as? String).flatMap(URL.init(string:)) }

    var body: some View {
        VStack(spacing: 24) {
            Button("Open security check") { presenting = true }.accessibilityIdentifier("harness.captcha.open")
            Text(result).accessibilityIdentifier("harness.captcha.result")
        }
        .sheet(isPresented: $presenting) {
            if let url {
                CaptchaChallengeView(sourceURL: url) { outcome in
                    switch outcome {
                    case .success(let token): result = "token received, \(token.count) characters"
                    case .failure(let failure): result = "failure: \(failure)"
                    }
                    CaptchaConsoleLog.write("result " + result)
                    presenting = false
                }
            }
        }
    }
}
#endif
