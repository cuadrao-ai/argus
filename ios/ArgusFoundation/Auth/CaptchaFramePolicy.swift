import Foundation

/// Which loads the CAPTCHA web view allows. The main frame may load only the configured page. Inner frames may load
/// that page, Cloudflare's challenge host over HTTPS, and the empty `about:blank` and `about:srcdoc` documents the
/// widget creates before it fills them; refusing those leaves the widget unable to finish.
enum CaptchaFramePolicy {
    static func allows(_ url: URL, mainFrame: Bool, source: URL) -> Bool {
        if mainFrame { return url == source }
        if url == source { return true }
        if url.scheme == "about" { return url.absoluteString == "about:blank" || url.absoluteString == "about:srcdoc" }
        return url.scheme == "https" && url.host == "challenges.cloudflare.com" && url.user == nil && url.password == nil
            && (url.port == nil || url.port == 443)
    }
}
