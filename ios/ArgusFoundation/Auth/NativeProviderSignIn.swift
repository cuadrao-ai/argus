import AuthenticationServices
import SwiftUI
import UIKit
import ArgusSession
#if canImport(GoogleSignIn)
import GoogleSignIn
import GoogleSignInSwift
#endif

/// Native Apple and Google sign-in switches. Both default off in Config/Development.xcconfig.
/// When a switch is off or its public ids are missing, its button is not shown and the
/// email flow is unchanged. See ../../AUTH_SETUP.md.
struct NativeProviderConfiguration: Equatable {
    struct Google: Equatable {
        let clientID: String
        let serverClientID: String?
    }

    let apple: Bool
    let google: Google?

    static let off = NativeProviderConfiguration(apple: false, google: nil)

    static func load(bundle: Bundle = .main) -> Self {
        #if !DEBUG
        return .off
        #else
        func flag(_ key: String) -> Bool {
            let value = bundle.object(forInfoDictionaryKey: key)
            return (value as? Bool == true) || (value as? String)?.lowercased() == "true"
        }
        func value(_ key: String) -> String? {
            guard let value = bundle.object(forInfoDictionaryKey: key) as? String,
                  !value.isEmpty, !value.contains("$(") else { return nil }
            return value
        }
        let apple = flag("ARGUS_APPLE_SIGN_IN_ENABLED")
        var google: Google?
        if apple, flag("ARGUS_GOOGLE_SIGN_IN_ENABLED"), let clientID = value("GOOGLE_SIGN_IN_IOS_CLIENT_ID"),
           let scheme = googleCallbackScheme(clientID), registeredSchemes(bundle).contains(scheme) {
            // GIDSignIn raises an Objective-C exception (a crash) when the reversed client id
            // isn't a registered URL scheme, so a half-configured build hides the button.
            let server = value("GOOGLE_SIGN_IN_WEB_CLIENT_ID").flatMap { googleCallbackScheme($0) == nil ? nil : $0 }
            google = Google(clientID: clientID, serverClientID: server)
        }
        return Self(apple: apple, google: google)
        #endif
    }

    /// "123-abc.apps.googleusercontent.com" -> "com.googleusercontent.apps.123-abc".
    static func googleCallbackScheme(_ clientID: String) -> String? {
        let suffix = ".apps.googleusercontent.com"
        guard clientID.hasSuffix(suffix) else { return nil }
        let id = clientID.dropLast(suffix.count)
        guard !id.isEmpty, id.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-") }) else { return nil }
        return "com.googleusercontent.apps." + id
    }

    private static func registeredSchemes(_ bundle: Bundle) -> Set<String> {
        let types = bundle.object(forInfoDictionaryKey: "CFBundleURLTypes") as? [[String: Any]] ?? []
        return Set(types.flatMap { ($0["CFBundleURLSchemes"] as? [String]) ?? [] })
    }
}

/// Apple and Google buttons for the connected create-account and sign-in screen.
/// Apple uses the system button (HIG); Google uses the official GoogleSignInSwift button.
struct ConnectedProviderButtons: View {
    let spanish: Bool
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var auth: ProfileAuthModel
    @State private var appleNonce: SignInNonce?
    @State private var failed = false

    var body: some View {
        let providers = auth.providers
        if providers.apple || providers.google != nil {
            VStack(spacing: 12) {
                if providers.apple {
                    AppleAuthorizationButton(busy: auth.busy) { request in
                        let nonce = SignInNonce()
                        appleNonce = nonce
                        request.requestedScopes = [.fullName, .email]
                        request.nonce = nonce.hashed
                    } onCompletion: { result in
                        completeApple(result)
                    }
                    .accessibilityIdentifier("cuadrao.auth.apple")
                }
                #if canImport(GoogleSignIn)
                if let google = providers.google {
                    GoogleSignInButton(scheme: colorScheme == .dark ? .dark : .light, style: .wide, state: auth.busy ? .disabled : .normal) {
                        Task { await signInWithGoogle(google) }
                    }
                    .disabled(auth.busy)
                    .accessibilityIdentifier("cuadrao.auth.google")
                }
                #endif
                if failed, !auth.busy, auth.state != .authenticated {
                    RegistrationNotice(symbol: "exclamationmark.circle",
                        title: CuadraoCopy.text("copy.nativeProviderSignIn.7fe06b0d57", spanish: spanish),
                        detail: CuadraoCopy.text("copy.nativeProviderSignIn.4574cd68ae", spanish: spanish))
                }
            }
            .padding(.bottom, 12)
            #if canImport(GoogleSignIn)
            .onOpenURL { url in _ = GIDSignIn.sharedInstance.handle(url) }
            #endif
        }
    }

    private func completeApple(_ result: Result<ASAuthorization, Error>) {
        let nonce = appleNonce
        appleNonce = nil
        switch result {
        case .failure(let error):
            // Cancelling the sheet is not a failure.
            failed = (error as? ASAuthorizationError)?.code != .canceled
        case .success(let authorization):
            guard let nonce,
                  let apple = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = apple.identityToken, let token = String(data: tokenData, encoding: .utf8) else {
                failed = true
                return
            }
            let code = apple.authorizationCodeText
            let formattedName = apple.fullName.map { PersonNameComponentsFormatter().string(from: $0) }
            let nameAuthorization: AppleNameAuthorization
            do { nameAuthorization = try auth.prepareAppleName(displayName: formattedName, subject: apple.user) }
            catch { failed = true; return }
            Task {
                failed = false
                let ok = await auth.signIn(with: IdentityTokenCredential(provider: .apple, idToken: token, nonce: nonce),
                                           appleAuthorizationCode: code, appleNameAuthorization: nameAuthorization)
                failed = !ok
            }
        }
    }

    #if canImport(GoogleSignIn)
    @MainActor
    private func signInWithGoogle(_ google: NativeProviderConfiguration.Google) async {
        guard !auth.busy, let presenter = Self.presenter() else { failed = true; return }
        failed = false
        let nonce = SignInNonce()
        let signIn = GIDSignIn.sharedInstance
        signIn.configuration = GIDConfiguration(clientID: google.clientID, serverClientID: google.serverClientID)
        do {
            let result = try await signIn.signIn(withPresenting: presenter, hint: nil, additionalScopes: nil, nonce: nonce.hashed)
            // The Supabase session is the identity; don't keep Google's own tokens on device.
            defer { signIn.signOut() }
            guard let idToken = result.user.idToken?.tokenString else { failed = true; return }
            let ok = await auth.signIn(with: IdentityTokenCredential(provider: .google, idToken: idToken, nonce: nonce,
                                                                    accessToken: result.user.accessToken.tokenString))
            failed = !ok
        } catch {
            failed = (error as? GIDSignInError)?.code != .canceled
        }
    }

    @MainActor
    private static func presenter() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }
        var top = scene?.keyWindow?.rootViewController
        while let presented = top?.presentedViewController { top = presented }
        return top
    }
    #endif
}

/// The one Apple request control: sign-in and the fresh authorization account deletion asks for.
struct AppleAuthorizationButton: View {
    let busy: Bool
    let onRequest: (ASAuthorizationAppleIDRequest) -> Void
    let onCompletion: (Result<ASAuthorization, Error>) -> Void
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        SignInWithAppleButton(.continue, onRequest: onRequest, onCompletion: onCompletion)
            .signInWithAppleButtonStyle(colorScheme == .dark ? .white : .black)
            .frame(maxWidth: .infinity, minHeight: 56, maxHeight: 56)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .disabled(busy)
    }
}

extension ASAuthorizationAppleIDCredential {
    var authorizationCodeText: String? { authorizationCode.flatMap { String(data: $0, encoding: .utf8) } }
}

struct NativeAppleCredentialChecker: AppleCredentialChecking {
    func state(for subject: String) async throws -> AppleCredentialState {
        try await withCheckedThrowingContinuation { continuation in
            ASAuthorizationAppleIDProvider().getCredentialState(forUserID: subject) { state, error in
                if error != nil { continuation.resume(throwing: SessionFailure.unavailable); return }
                switch state {
                case .authorized: continuation.resume(returning: .authorized)
                case .revoked: continuation.resume(returning: .revoked)
                case .notFound: continuation.resume(returning: .notFound)
                case .transferred: continuation.resume(returning: .transferred)
                @unknown default: continuation.resume(throwing: SessionFailure.unavailable)
                }
            }
        }
    }
}
