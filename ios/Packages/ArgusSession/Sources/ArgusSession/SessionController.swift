import Auth
import Foundation

/// The sole native session owner. Product identity comes from Argus /me, not a
/// decoded JWT or a parallel profile cache. Account API values are transported without client financial rules.
public actor SessionController {
    private let configuration: SessionConfiguration
    private let vault: CredentialVault
    private let transport: SessionTransport
    private let appleChecker: any AppleCredentialChecking
    private var auth: AuthClient?
    private var mutating = false
    private var protectedRequests = 0
    private var credentialValidationGeneration: UInt64 = 0
    private var state = SessionSnapshot(phase: .signedOut, profile: nil, revision: 0)

    public init(configuration: SessionConfiguration, appleChecker: any AppleCredentialChecking) throws {
        self.appleChecker = appleChecker
        self.configuration = configuration
        self.vault = CredentialVault(backing: DeviceKeychain(service: configuration.keychainService), prefix: configuration.storagePrefix)
        self.transport = SessionTransport()
    }
    init(configuration: SessionConfiguration, storage: any AuthLocalStorage, appleChecker: any AppleCredentialChecking = UnavailableAppleCredentialChecker(), fetch: @escaping AuthClient.FetchHandler) throws {
        self.appleChecker = appleChecker
        self.configuration = configuration
        self.vault = CredentialVault(backing: storage, prefix: configuration.storagePrefix)
        self.transport = SessionTransport(fetch: fetch)
    }
    public func snapshot() -> SessionSnapshot { state }

    /// Whether the keychain still holds a session, read without the network.
    public func hasStoredSession() -> Bool { (try? vault.session()) != nil }

    public func requestCredentialRevalidation() throws -> SessionSnapshot {
        credentialValidationGeneration &+= 1
        do {
            // Admit notifications during adoption without retiring proof owned by its mutation.
            if !mutating, try restoreDeletionState() { return state }
            if try vault.deletionJournal()?.phase == .uncertain {
                setState(.accountDeletionUncertain)
                return state
            }
            if try vault.pending() != nil {
                setState(.signOutPending)
                return state
            }
            let method = try vault.signInMethod()
            if method == .apple || (method == nil && state.appleIdentity != nil) {
                setState(.credentialValidationRequired, profile: state.profile, appleIdentity: state.appleIdentity)
            }
            return state
        } catch {
            if state.phase != .signOutPending && state.phase != .accountDeletionUncertain && state.phase != .accountDeletionPending {
                setState(.credentialValidationRequired)
            }
            throw SessionFailure.storageUnavailable
        }
    }

    public func restore(onValidationRequired: @Sendable (SessionSnapshot) async -> Void = { _ in }) async throws -> SessionSnapshot {
        guard !mutating else { throw SessionFailure.busy }
        if try restoreDeletionState() { return state }
        try vault.prunePregrantAppleName()
        do {
            if try vault.pending() != nil {
                try beginMutation(); defer { mutating = false }
                setState(.signOutPending)
                return try await performPendingRevoke()
            }
        } catch {
            if state.phase != .signOutPending { setState(.credentialValidationRequired) }
            await onValidationRequired(state)
            throw safe(error)
        }
        let method: SessionSignInMethod?
        do { method = try vault.signInMethod() }
        catch {
            setState(.credentialValidationRequired)
            await onValidationRequired(state)
            throw SessionFailure.storageUnavailable
        }
        if state.phase == .authenticated, let method, method != .apple {
            return try await loadProfile(using: activeAuth(), epoch: vault.epoch())
        }
        try beginMutation(); defer { mutating = false }
        guard let existing = try vault.session() else { endAccountEpoch(as: .signedOut); return state }
        if existing.user.isAnonymous { setState(.unsupportedAnonymousSession); return state }
        _ = try await loadProfile(using: activeAuth(), epoch: vault.epoch(), onValidationRequired: onValidationRequired)
        _ = await resumeAppleName()
        return state
    }

    public func login(email: String, password: String, captchaToken: String) async throws -> SessionSnapshot {
        try beginMutation(); defer { mutating = false }
        try requireEntry()
        let response = try await entry(path: "auth/login", body: ["email": email, "password": password, "captcha_token": captchaToken])
        guard let credentials = response.session else { throw SessionFailure.invalidResponse }
        return try await adopt(credentials, method: .email)
    }

    public func signup(email: String, password: String, captchaToken: String, language: String,
                       displayName: String? = nil, ageConfirmation: AgeConfirmation? = nil) async throws -> SignupOutcome {
        try beginMutation(); defer { mutating = false }
        try requireEntry()
        guard let ageConfirmation else { throw SessionFailure.rejected(status: 422, code: "age_confirmation_required") }
        var body = ["email": email, "password": password, "captcha_token": captchaToken, "language": language,
                    "age_confirmed_at": ageConfirmation.timestamp]
        if let displayName { body["display_name"] = displayName }
        let response = try await entry(path: "auth/signup", body: body)
        guard let credentials = response.session else { return .confirmationRequired }
        return .authenticated(try await adopt(credentials, method: .email))
    }

    /// Native Apple or Google sign-in. The provider's ID token and the raw nonce go to
    /// Supabase Auth's id_token grant on an isolated in-memory client; the issued tokens
    /// then take the same journaled adoption path as email sign-in (pending journal,
    /// setSession, then the canonical /me profile). If Argus refuses the new session
    /// (for example the private-alpha allowlist at /me), it is revoked before returning.
    /// Persist the callback before starting asynchronous sign-in. A later callback
    /// without a name can recover this input only for the same Apple subject.
    public nonisolated func prepareAppleName(displayName: String?, subject: String) throws -> AppleNameAuthorization {
        do { return try vault.prepareAppleName(displayName: displayName, subject: subject) }
        catch let failure as SessionFailure { throw failure }
        catch { throw SessionFailure.storageUnavailable }
    }

    public func signIn(with credential: IdentityTokenCredential, appleAuthorizationCode: String? = nil,
                       appleNameAuthorization: AppleNameAuthorization? = nil) async throws -> ProviderSignInOutcome {
        try beginMutation(); defer { mutating = false }
        try requireEntry()
        guard credential.wellFormed else { throw SessionFailure.invalidResponse }
        if appleNameAuthorization != nil && credential.provider != .apple { throw SessionFailure.invalidResponse }
        let initialName = try appleNameAuthorization.flatMap { try vault.appleName(for: $0) }
        if credential.provider != .apple { try vault.removePregrantAppleName() }
        let exchange = makeAuth(storage: ExchangeStorage(), fetch: transport.sdkFetch(origin: configuration.supabaseURL))
        let issued: Session
        do {
            issued = try await exchange.signInWithIdToken(credentials: OpenIDConnectCredentials(
                provider: credential.provider == .apple ? .apple : .google, idToken: credential.idToken,
                accessToken: credential.accessToken, nonce: credential.nonce.raw))
        } catch {
            if case let AuthError.api(_, code, _, response) = error {
                if response.statusCode >= 500 { throw SessionFailure.unavailable }
                try vault.removePregrantAppleName()
                throw SessionFailure.rejected(status: response.statusCode, code: bounded(code.rawValue))
            }
            throw safe(error)
        }
        if let appleNameAuthorization { try vault.check(appleNameAuthorization.epoch) }
        guard !issued.user.isAnonymous else { try vault.removePregrantAppleName(); throw SessionFailure.unsupportedAnonymousTransfer }
        let boundName = initialName.map { BoundAppleNameIntent(intent: $0, userID: issued.user.id, grantID: UUID()) }
        do {
            let snapshot = try await adopt(Credentials(accessToken: issued.accessToken, refreshToken: issued.refreshToken), method: credential.provider == .apple ? .apple : .google, appleName: boundName)
            guard credential.provider == .apple else { return .init(session: snapshot, appleCapture: nil) }
            guard snapshot.phase == .authenticated else {
                let needsFreshCode = snapshot.phase == .credentialValidationRequired || snapshot.phase == .reauthenticationRequired
                return .init(session: snapshot, appleCapture: needsFreshCode ? .freshAuthorizationRequired : nil,
                             appleName: boundName == nil ? nil : .pending(.credentialValidationRequired))
            }
            let capture: AppleCaptureOutcome
            if let appleAuthorizationCode {
                do {
                    try await captureAppleCode(appleAuthorizationCode, expectedIdentity: snapshot)
                    capture = .saved
                } catch {
                    let failure = safe(error)
                    capture = failure == .rejected(status: 400, code: "apple_authorization_invalid")
                        ? .freshAuthorizationRequired : .failed(failure)
                }
            } else { capture = .freshAuthorizationRequired }
            let name = await resumeAppleName()
            return .init(session: state, appleCapture: capture, appleName: name)
        } catch {
            // adopt() has journaled the issued session as pending; revoke it now so a
            // refused provider account doesn't leave the person on the sign-out screen.
            _ = try? await performPendingRevoke()
            throw error
        }
    }

    public func retryAppleNameInitialization(expectedIdentity: SessionSnapshot) async throws -> SessionSnapshot {
        guard sameIdentity(as: expectedIdentity) else { throw SessionFailure.staleOperation }
        try beginMutation(); defer { mutating = false }
        _ = try await initializePendingAppleName()
        return state
    }

    private func resumeAppleName() async -> AppleNameSaveOutcome? {
        do { return try await initializePendingAppleName() ? .saved : nil }
        catch {
            let failure = safe(error)
            if failure == .storageUnavailable, state.phase == .authenticated {
                setState(.credentialValidationRequired, profile: state.profile, appleIdentity: state.appleIdentity)
            }
            return .pending(failure)
        }
    }

    private func initializePendingAppleName() async throws -> Bool {
        guard let bound = try vault.pendingAppleName() else { return false }
        guard state.phase == .authenticated else { throw SessionFailure.credentialValidationRequired }
        let epoch = vault.epoch()
        guard try vault.signInMethod() == .apple, UUID(uuidString: state.profile?.id ?? "") == bound.userID,
              state.appleIdentity?.subject == bound.intent.subject else {
            try vault.acknowledgeAppleName(bound, epoch: epoch)
            return false
        }
        var request = URLRequest(url: configuration.argusAPIURL.appending(path: "api/v1/me/apple-name"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoded(["display_name": bound.intent.displayName])
        let result = try await authenticatedResponse(using: activeAuth(), epoch: epoch, request: request)
        struct NameEnvelope: Decodable {
            let user: SessionProfile
            let appleIdentity: AppleIdentity?
            enum CodingKeys: String, CodingKey { case user; case appleIdentity = "apple_identity" }
        }
        let envelope = try JSONDecoder().decode(NameEnvelope.self, from: result.0)
        guard UUID(uuidString: envelope.user.id) == bound.userID,
              envelope.appleIdentity?.subject == bound.intent.subject else { throw SessionFailure.invalidResponse }
        try vault.check(epoch)
        try vault.acknowledgeAppleName(bound, epoch: epoch)
        setState(.authenticated, profile: envelope.user, appleIdentity: envelope.appleIdentity)
        return true
    }

    public func captureAppleAuthorizationCode(_ code: String, expectedIdentity: SessionSnapshot) async throws {
        try beginMutation(); defer { mutating = false }
        try await captureAppleCode(code, expectedIdentity: expectedIdentity)
    }

    private func captureAppleCode(_ code: String, expectedIdentity: SessionSnapshot) async throws {
        guard !code.isEmpty, code.utf8.count <= 512, code.allSatisfy(\.isASCII) else {
            throw SessionFailure.invalidResponse
        }
        guard sameIdentity(as: expectedIdentity) else { throw SessionFailure.staleOperation }
        var request = URLRequest(url: configuration.argusAPIURL.appending(path: "api/v1/auth/apple/authorization-code"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoded(["authorization_code": code])
        // The one-time code may have been consumed even when the response is uncertain.
        _ = try await authenticatedResponse(using: activeAuth(), epoch: vault.epoch(), request: request, retryUnauthorized: false)
    }

    public func profile() async throws -> SessionSnapshot {
        try await restore()
    }

    public func setPrimaryCurrency(_ currency: String, expectedIdentity: SessionSnapshot) async throws -> SessionSnapshot {
        try await patchProfile(["currency_override": currency], expectedIdentity: expectedIdentity)
    }

    /// An empty preferred name clears it on the server.
    public func setNames(displayName: String, preferredName: String, expectedIdentity: SessionSnapshot) async throws -> SessionSnapshot {
        try await patchProfile(["display_name": displayName, "preferred_name": preferredName], expectedIdentity: expectedIdentity)
    }

    private func patchProfile(_ fields: [String: String], expectedIdentity: SessionSnapshot) async throws -> SessionSnapshot {
        guard state.phase == .authenticated, state.revision == expectedIdentity.revision,
              state.profile?.id == expectedIdentity.profile?.id else { throw SessionFailure.staleOperation }
        try beginMutation(); defer { mutating = false }
        if try vault.pending() != nil { throw SessionFailure.pendingSignOut }
        let epoch = vault.epoch()
        var request = URLRequest(url: configuration.argusAPIURL.appending(path: "api/v1/me"))
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoded(fields)
        _ = try await authenticatedResponse(using: activeAuth(), epoch: epoch, request: request)
        return try await loadProfile(using: activeAuth(), epoch: epoch)
    }

    public func signOut() async throws -> SessionSnapshot {
        try beginMutation(); defer { mutating = false }
        try requireNoUncertainDeletion()
        if try restoreDeletionState() { return state }
        if try vault.pending() == nil {
            guard let current = try vault.session() else { try vault.removePregrantAppleName(); endAccountEpoch(as: .signedOut); return state }
            guard !current.user.isAnonymous else { throw SessionFailure.unsupportedAnonymousTransfer }
        }
        try suspendUsableSession()
        return try await performPendingRevoke()
    }

    public func retryPendingSignOut() async throws -> SessionSnapshot {
        try beginMutation(); defer { mutating = false }
        try requireNoUncertainDeletion()
        if try restoreDeletionState() { return state }
        guard try vault.pending() != nil else { return state }
        try suspendUsableSession()
        return try await performPendingRevoke()
    }

    private func beginMutation() throws {
        guard !mutating else { throw SessionFailure.busy }
        mutating = true
    }
    private func requireEntry() throws {
        try requireNoUncertainDeletion()
        if try vault.pending() != nil { setState(.signOutPending); throw SessionFailure.pendingSignOut }
        if let existing = try vault.session() {
            if existing.user.isAnonymous {
                setState(.unsupportedAnonymousSession)
                throw SessionFailure.unsupportedAnonymousTransfer
            }
            throw SessionFailure.rejected(status: 409, code: "already_authenticated")
        }
        try vault.preflight()
    }
    private func activeAuth(adoptingMethod: SessionSignInMethod? = nil, adoptingName: BoundAppleNameIntent? = nil) -> AuthClient {
        if let auth { return auth }
        let client = makeAuth(storage: EpochStorage(vault: vault, epoch: vault.epoch(), adoptingMethod: adoptingMethod, adoptingName: adoptingName), fetch: transport.sdkFetch(origin: configuration.supabaseURL))
        auth = client
        return client
    }
    private func makeAuth(storage: any AuthLocalStorage, fetch: @escaping AuthClient.FetchHandler) -> AuthClient {
        AuthClient(url: configuration.supabaseURL.appending(path: "auth/v1"),
                   headers: ["apikey": configuration.publicAnonKey], storageKey: "argus.session",
                   localStorage: storage, logger: nil, fetch: fetch, autoRefreshToken: false)
    }
    private func setState(_ phase: SessionSnapshot.Phase, profile: SessionProfile? = nil, appleIdentity: AppleIdentity? = nil) {
        state = .init(phase: phase, profile: profile, revision: vault.epoch(), appleIdentity: appleIdentity)
    }
    private func endAccountEpoch(as phase: SessionSnapshot.Phase) {
        vault.retire()
        auth = nil
        setState(phase)
    }
    private struct EntryResponse: Decodable {
        let session: Credentials?
    }
    private struct Credentials: Decodable {
        let accessToken: String
        let refreshToken: String
        enum CodingKeys: String, CodingKey { case accessToken = "access_token", refreshToken = "refresh_token" }
    }
    private func entry(path: String, body: [String: String]) async throws -> EntryResponse {
        do {
            var request = URLRequest(url: configuration.argusAPIURL.appending(path: "api/v1/" + path))
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(body)
            let (data, response) = try await transport.send(request, origin: configuration.argusAPIURL)
            guard (200..<300).contains(response.statusCode) else { throw problem(data, status: response.statusCode) }
            return try JSONDecoder().decode(EntryResponse.self, from: data)
        } catch { throw safe(error) }
    }
    private func adopt(_ credentials: Credentials, method: SessionSignInMethod, appleName: BoundAppleNameIntent? = nil) async throws -> SessionSnapshot {
        guard !credentials.accessToken.isEmpty, !credentials.refreshToken.isEmpty else { throw SessionFailure.invalidResponse }
        // Journal before SDK adoption: a crash or swallowed persistence error must not
        // leave an issued server session invisible to the next launch.
        setState(.signOutPending)
        try vault.savePending(.init(accessToken: credentials.accessToken, refreshToken: credentials.refreshToken))
        endAccountEpoch(as: .signOutPending)
        let epoch = vault.epoch()
        let client = activeAuth(adoptingMethod: method, adoptingName: appleName)
        do {
            let session = try await client.setSession(accessToken: credentials.accessToken, refreshToken: credentials.refreshToken)
            try vault.check(epoch)
            guard let stored = try vault.session(), stored.refreshToken == session.refreshToken else { throw SessionFailure.storageUnavailable }
            guard !session.user.isAnonymous else { throw SessionFailure.unsupportedAnonymousTransfer }
            _ = try await loadProfile(using: client, epoch: epoch, validateCredential: false)
            try vault.removePending()
            if let appleName { try vault.removePromotedAppleName(appleName.intent.id, epoch: epoch) }
        } catch {
            let failure = safe(error)
            let preserveCallback: Bool
            if case .rejected(let status, _) = failure { preserveCallback = status >= 500 }
            else { preserveCallback = failure == .unavailable || failure == .storageUnavailable }
            try suspendUsableSession(discardAppleName: !preserveCallback)
            throw safe(error)
        }
        return try await validateAppleCredential(epoch: epoch)
    }

    private func loadProfile(using client: AuthClient, epoch: UInt64, validateCredential: Bool = true,
                             onValidationRequired: @Sendable (SessionSnapshot) async -> Void = { _ in }) async throws -> SessionSnapshot {
        let method = try vault.signInMethod()
        if method == .apple || (method == nil && state.appleIdentity != nil) {
            setState(.credentialValidationRequired)
            await onValidationRequired(state)
            try vault.check(epoch)
        }
        let request = URLRequest(url: configuration.argusAPIURL.appending(path: "api/v1/me"))
        let result = try await authenticatedResponse(using: client, epoch: epoch, request: request, access: .validation)
        do {
            struct ProfileEnvelope: Decodable {
                let user: SessionProfile
                let appleIdentity: AppleIdentity?
                enum CodingKeys: String, CodingKey { case user; case appleIdentity = "apple_identity" }
            }
            let envelope = try JSONDecoder().decode(ProfileEnvelope.self, from: result.0)
            guard UUID(uuidString: envelope.user.id) == (try vault.session())?.user.id else {
                try suspendUsableSession()
                throw SessionFailure.invalidResponse
            }
            try vault.check(epoch)
            setState(.credentialValidationRequired, profile: envelope.user, appleIdentity: envelope.appleIdentity)
            if method == nil && envelope.appleIdentity != nil { await onValidationRequired(state) }
            return validateCredential ? try await validateAppleCredential(epoch: epoch) : state
        } catch { throw safe(error) }
    }

    private func validateAppleCredential(epoch: UInt64) async throws -> SessionSnapshot {
        try vault.check(epoch)
        let method = try vault.signInMethod()
        if method == nil && state.appleIdentity != nil || method == .apple && state.appleIdentity == nil {
            setState(.reauthenticationRequired)
            return state
        }
        if method == .apple, let identity = state.appleIdentity {
            let generation = credentialValidationGeneration
            let answer: AppleCredentialState
            do { answer = try await appleChecker.state(for: identity.subject) }
            catch {
                try vault.check(epoch)
                return state
            }
            try vault.check(epoch)
            guard generation == credentialValidationGeneration else { return state }
            switch answer {
            case .authorized: break
            case .transferred: return state
            case .revoked, .notFound:
                try suspendUsableSession()
                return try await performPendingRevoke()
            }
        }
        setState(.authenticated, profile: state.profile, appleIdentity: state.appleIdentity)
        return state
    }

    private enum AuthenticatedAccess { case validated, validation }

    private func checkAccess(_ access: AuthenticatedAccess, identity: SessionSnapshot) throws {
        try requireNoUncertainDeletion()
        if access == .validation { return }
        guard state.phase == .authenticated else { throw SessionFailure.credentialValidationRequired }
        guard sameIdentity(as: identity) else { throw SessionFailure.staleOperation }
    }

    private func sameIdentity(as identity: SessionSnapshot) -> Bool {
        state.phase == .authenticated && identity.phase == .authenticated
            && state.revision == identity.revision && state.profile?.id == identity.profile?.id
    }
    /// Shared authenticated transport for /me and financial records. SDK owns
    /// refresh coalescing; this layer permits only one 401 refresh/retry.
    private func authenticatedResponse(using client: AuthClient, epoch: UInt64,
                                       request: URLRequest, retryUnauthorized: Bool = true, access: AuthenticatedAccess = .validated) async throws -> (Data, HTTPURLResponse) {
        try requireNoUncertainDeletion()
        protectedRequests += 1
        defer { protectedRequests -= 1 }
        var retiring = false
        let identity = state
        do {
            try checkAccess(access, identity: identity)
            try vault.check(epoch)
            let session = try await client.session
            try vault.check(epoch)
            try checkAccess(access, identity: identity)
            guard !session.user.isAnonymous else { throw SessionFailure.unsupportedAnonymousTransfer }
            var authorized = request
            authorized.setValue("Bearer " + session.accessToken, forHTTPHeaderField: "Authorization")
            var result = try await transport.send(authorized, origin: configuration.argusAPIURL)
            try vault.check(epoch)
            try checkAccess(access, identity: identity)
            if result.1.statusCode == 401 && retryUnauthorized {
                let refreshed = try await client.refreshSession()
                try vault.check(epoch)
                try checkAccess(access, identity: identity)
                authorized.setValue("Bearer " + refreshed.accessToken, forHTTPHeaderField: "Authorization")
                result = try await transport.send(authorized, origin: configuration.argusAPIURL)
                try vault.check(epoch)
                try checkAccess(access, identity: identity)
            }
            guard result.1.statusCode != 401 else {
                retiring = true
                try suspendUsableSession()
                throw SessionFailure.unauthorized
            }
            guard (200..<300).contains(result.1.statusCode) else { throw problem(result.0, status: result.1.statusCode) }
            return result
        } catch {
            if vault.epoch() != epoch {
                if retiring { throw safe(error) }
                throw SessionFailure.staleOperation
            }
            do { try vault.check(epoch) }
            catch { try suspendUsableSession(); throw SessionFailure.storageUnavailable }
            if (error as? AuthError) == .sessionMissing {
                endAccountEpoch(as: .signedOut)
                try vault.removeSession()
                throw SessionFailure.unauthorized
            }
            if case let AuthError.api(_, _, _, response) = error,
               [400, 401, 403].contains(response.statusCode) {
                try suspendUsableSession()
                throw SessionFailure.unauthorized
            }
            throw safe(error)
        }
    }
    private func suspendUsableSession(discardAppleName: Bool = true) throws {
        // Invalidate delivery and SDK writes before journal I/O can fail. Actual
        // credential removal still waits for a successful durable pending write.
        endAccountEpoch(as: .signOutPending)
        if let pending = try vault.pending() {
            // A previous failed write may have left this journal only in memory.
            try vault.savePending(pending)
        } else if let current = try vault.session() {
            try vault.savePending(.init(accessToken: current.accessToken, refreshToken: current.refreshToken))
        }
        if discardAppleName { try vault.removePregrantAppleName() }
        try vault.removeSession()
    }

    private func performPendingRevoke() async throws -> SessionSnapshot {
        guard let pending = try vault.pending() else { endAccountEpoch(as: .signedOut); return state }
        setState(.signOutPending)
        let storage = RevocationStorage(vault: vault)
        let receipt = RevokeReceipt()
        let origin = configuration.supabaseURL
        let transport = self.transport
        let client = makeAuth(storage: storage, fetch: { request in
            let (data, response) = try await transport.send(request, origin: origin)
            receipt.observe(request, response: response)
            return (data, response)
        })
        do {
            // Refresh first: SDK signOut silently accepts an expired-JWT 401, which
            // does not prove the refresh session was revoked. Rotations persist first.
            _ = try await client.refreshSession(refreshToken: pending.refreshToken)
            try storage.check()
            try await client.signOut(scope: .local)
            try storage.check()
            guard receipt.confirmed else { return state }
        } catch {
            try storage.check()
            guard (error as? AuthError) == .sessionMissing else {
                if (error as? SessionFailure) == .storageUnavailable { throw SessionFailure.storageUnavailable }
                return state
            }
        }
        // Clear residual SDK state before the pending marker, including interrupted
        // local cleanup from an earlier launch.
        try vault.removeSession()
        try vault.removePending()
        endAccountEpoch(as: .signedOut)
        return state
    }
    private func problem(_ data: Data, status: Int) -> SessionFailure {
        struct Problem: Decodable { let code: String? }
        let raw = (try? JSONDecoder().decode(Problem.self, from: data))?.code
        let code = raw.flatMap(bounded)
        if status >= 500 && code == nil { return .unavailable }
        return .rejected(status: status, code: code)
    }
    /// Only a bounded identifier reaches UI, never arbitrary server detail.
    private func bounded(_ value: String) -> String? {
        !value.isEmpty && value.count <= 80 && value.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_") } ? value : nil
    }
    private func safe(_ error: any Error) -> SessionFailure {
        if let failure = error as? SessionFailure { return failure }
        if error is DecodingError { return .invalidResponse }
        if (error as? AuthError) == .sessionMissing { return .unauthorized }
        return .unavailable
    }

    /// Resolves only this owner's journal; never uses SDK refresh or retries an Apple code.
    public func deleteAccount(expectedIdentity: SessionSnapshot,
                              freshAppleAuthorizationCode: String? = nil) async throws -> AccountDeletionResult {
        guard sameIdentity(as: expectedIdentity) else { throw SessionFailure.staleOperation }
        guard protectedRequests == 0 else { throw SessionFailure.busy }
        try requireNoUncertainDeletion()
        let body = try AccountDeletionRequest(code: freshAppleAuthorizationCode)
        try beginMutation(); defer { mutating = false }
        guard let userID = UUID(uuidString: expectedIdentity.profile?.id ?? ""),
              let session = try vault.session(), session.user.id == userID else { throw SessionFailure.staleOperation }
        guard session.expiresAt > Date().timeIntervalSince1970 else { throw SessionFailure.unauthorized }
        let journal = AccountDeletionJournal(id: UUID(), userID: userID, initiatingRevision: vault.epoch(), phase: .uncertain,
                                             retryAfter: nil, canRetry: true)
        return try await performDeletion(journal, session: session, body: body, resuming: false)
    }

    public func resumePendingAccountDeletion(freshAppleAuthorizationCode: String? = nil) async throws -> AccountDeletionResult {
        let body = try AccountDeletionRequest(code: freshAppleAuthorizationCode)
        try beginMutation(); defer { mutating = false }
        guard let journal = try vault.deletionJournal(), journal.phase == .uncertain else { throw SessionFailure.staleOperation }
        guard let session = try vault.session() else {
            return .uncertain(userID: journal.userID, retryAfter: journal.retryAfter, canRetry: false, recovery: journal.recovery)
        }
        guard session.user.id == journal.userID else { throw SessionFailure.staleOperation }
        guard journal.canRetry, session.expiresAt > Date().timeIntervalSince1970 else {
            return .uncertain(userID: journal.userID, retryAfter: journal.retryAfter, canRetry: false, recovery: journal.recovery)
        }
        if let retry = journal.retryAfter, retry > Date() { throw SessionFailure.busy }
        return try await performDeletion(journal, session: session, body: body, resuming: true)
    }

    public func accountDeletionStatus(userID: UUID) throws -> AccountDeletionResult? {
        guard let journal = try vault.deletionJournal(userID: userID) else { return nil }
        switch journal.phase {
        case .pending: return .pending(userID: userID)
        case .completed:
            guard try vault.session() == nil, try vault.pending() == nil else { return nil }
            return .completed(.init(userID: userID, initiatingRevision: journal.initiatingRevision, commandID: journal.id))
        case .uncertain:
            let proof = try vault.session()
            return .uncertain(userID: userID, retryAfter: journal.retryAfter,
                canRetry: journal.canRetry && proof?.user.id == userID && (proof?.expiresAt ?? 0) > Date().timeIntervalSince1970, recovery: journal.recovery)
        }
    }

    /// Relaunch readback derives from the same journal; no separate acknowledgement store.
    public func accountDeletionStatuses() throws -> [AccountDeletionResult] {
        try vault.deletionOwners().sorted { $0.uuidString < $1.uuidString }.compactMap { try accountDeletionStatus(userID: $0) }
    }

    /// Validate ownership and run idempotent cleanup without letting another account enter between them.
    public func acknowledgeConfirmedAccountDeletion(_ receipt: ConfirmedAccountDeletion,
                                                   cleanup: @Sendable (UUID) throws -> Void) throws {
        try beginMutation(); defer { mutating = false }
        guard try vault.session() == nil, try vault.pending() == nil,
              let journal = try vault.deletionJournal(userID: receipt.userID), journal.phase == .completed,
              journal.id == receipt.commandID, journal.userID == receipt.userID,
              journal.initiatingRevision == receipt.initiatingRevision else { throw SessionFailure.staleOperation }
        try retire(journal, cleanup: cleanup)
    }

    /// An accepted (202) deletion already retired its session, so its local data goes the same way, keyed by its journal.
    public func acknowledgeAcceptedAccountDeletion(userID: UUID, cleanup: @Sendable (UUID) throws -> Void) throws {
        try beginMutation(); defer { mutating = false }
        guard try vault.session() == nil, try vault.pending() == nil,
              let journal = try vault.deletionJournal(userID: userID), journal.phase == .pending else { throw SessionFailure.staleOperation }
        try retire(journal, cleanup: cleanup)
    }

    /// The journal is the cleanup obligation, so it goes only after the cleanup succeeds.
    private func retire(_ journal: AccountDeletionJournal, cleanup: @Sendable (UUID) throws -> Void) throws {
        let epoch = vault.epoch()
        try cleanup(journal.userID)
        try vault.removeDeletionJournal(epoch: epoch, userID: journal.userID)
    }

    private func requireNoUncertainDeletion() throws {
        if let journal = try vault.deletionJournal(), journal.phase == .uncertain {
            throw SessionFailure.accountDeletionInProgress
        }
    }

    private func restoreDeletionState() throws -> Bool {
        guard let journal = try vault.deletionJournal() else { return false }
        if journal.phase == .uncertain {
            setState(.accountDeletionUncertain)
            return true
        }
        if let session = try vault.session(), session.user.id != journal.userID { return false }
        // An interrupted token removal must finish before ordinary SDK adoption.
        endAccountEpoch(as: .signedOut)
        try vault.removeSession()
        try vault.removePending()
        return true
    }

    private func performDeletion(_ existing: AccountDeletionJournal, session: Session,
                                 body: AccountDeletionRequest, resuming: Bool) async throws -> AccountDeletionResult {
        let epoch = vault.epoch()
        var journal = existing
        // Persist before dispatch, including before cancellation can reach transport.
        try vault.saveDeletionJournal(journal, epoch: epoch)
        let identity = state
        let validationGeneration = credentialValidationGeneration
        setState(.accountDeletionUncertain)
        var request = URLRequest(url: configuration.argusAPIURL.appending(path: "api/v1/account/delete"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + session.accessToken, forHTTPHeaderField: "Authorization")
        request.httpBody = try encoded(body)
        let result: AccountDeletionResponse
        do {
            try Task.checkCancellation()
            let response = try await transport.send(request, origin: configuration.argusAPIURL)
            try vault.check(epoch)
            guard try vault.session()?.user.id == journal.userID else { throw SessionFailure.staleOperation }
            result = AccountDeletionResponse.parse(response.0, response: response.1)
        } catch {
            if (error as? SessionFailure) == .staleOperation { throw SessionFailure.staleOperation }
            guard vault.epoch() == epoch else { throw SessionFailure.staleOperation }
            try vault.check(epoch)
            return .uncertain(userID: journal.userID, retryAfter: journal.retryAfter, canRetry: session.expiresAt > Date().timeIntervalSince1970, recovery: journal.recovery)
        }
        switch result {
        case .done, .pending:
            let done: Bool
            if case .done = result { done = true } else { done = false }
            journal.phase = done ? .completed : .pending
            journal.canRetry = false
            journal.retryAfter = nil
            try vault.saveDeletionJournal(journal, epoch: epoch)
            // Fence SDK writes before deleting its stored session. No network logout or token refresh.
            endAccountEpoch(as: done ? .signedOut : .accountDeletionPending)
            try vault.removeSession()
            try vault.removePending()
            return done ? .completed(.init(userID: journal.userID, initiatingRevision: journal.initiatingRevision, commandID: journal.id)) : .pending(userID: journal.userID)
        case .uncertain(let retry, let canRetry):
            journal.retryAfter = retry; journal.canRetry = canRetry; journal.recovery = nil
            try vault.saveDeletionJournal(journal, epoch: epoch)
            return .uncertain(userID: journal.userID, retryAfter: retry, canRetry: canRetry && session.expiresAt > Date().timeIntervalSince1970, recovery: nil)
        case .refused(let refusal):
            // A refusal to this retry cannot erase an earlier lost response's uncertainty.
            if resuming {
                journal.recovery = refusal
                if case .rateLimited(let retry) = refusal { journal.retryAfter = retry }
                if refusal == .disabled || refusal == .forbidden || refusal == .invalidRequest { journal.canRetry = false }
                try vault.saveDeletionJournal(journal, epoch: epoch)
                return .uncertain(userID: journal.userID, retryAfter: journal.retryAfter,
                                  canRetry: journal.canRetry, recovery: refusal)
            } else {
                try vault.removeDeletionJournal(epoch: epoch)
                if validationGeneration == credentialValidationGeneration {
                    state = identity
                } else {
                    setState(.credentialValidationRequired, profile: identity.profile, appleIdentity: identity.appleIdentity)
                    let method = try vault.signInMethod()
                    if !(method == .apple || method == nil && identity.appleIdentity != nil) { state = identity }
                }
            }
            return .refused(refusal)
        }
    }

}


extension SessionController {
    public func financialAccounts(expectedIdentity: SessionSnapshot) async throws -> [FinancialAccount] {
        struct Envelope: Decodable { let accounts: [FinancialAccount] }
        let data = try await financialRequest(expectedIdentity: expectedIdentity)
        do { return try JSONDecoder().decode(Envelope.self, from: data).accounts }
        catch { throw SessionFailure.invalidResponse }
    }

    public func financialAccount(id: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialAccount {
        try decodeAccount(await financialRequest(path: "/" + id.uuidString, expectedIdentity: expectedIdentity))
    }

    public func createFinancialAccount(_ request: CreateFinancialAccountRequest,
                                       expectedIdentity: SessionSnapshot) async throws -> FinancialAccount {
        try decodeAccount(await financialRequest(method: "POST", body: encoded(request),
            key: request.idempotencyKey.uuidString, expectedIdentity: expectedIdentity))
    }

    public func updateFinancialAccount(id: UUID, request: EditFinancialAccountRequest,
                                       expectedIdentity: SessionSnapshot) async throws -> FinancialAccount {
        try decodeAccount(await financialRequest(path: "/" + id.uuidString, method: "PATCH",
            body: encoded(request), expectedIdentity: expectedIdentity))
    }

    public func writeOpening(id: UUID, request: WriteOpeningRequest, key: UUID? = nil,
                             expectedIdentity: SessionSnapshot) async throws -> FinancialAccount {
        try decodeAccount(await financialRequest(path: "/" + id.uuidString + "/opening", method: "PUT",
            body: encoded(request), key: key?.uuidString, expectedIdentity: expectedIdentity))
    }

    func encoded(_ value: some Encodable) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return try encoder.encode(value)
    }
    private func decodeAccount(_ data: Data) throws -> FinancialAccount {
        do { return try JSONDecoder().decode(FinancialAccount.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }
    func financialRequest(route: String = "financial-accounts", path: String = "", method: String = "GET", body: Data? = nil,
                                  key: String? = nil, query: [URLQueryItem] = [], contentType: String = "application/json",
                                  headers: [String: String] = [:], expectedIdentity: SessionSnapshot) async throws -> Data {
        guard expectedIdentity.phase == .authenticated, expectedIdentity.profile != nil else { throw SessionFailure.unauthorized }
        guard state.phase == .authenticated, state.revision == expectedIdentity.revision,
              state.profile?.id == expectedIdentity.profile?.id else { throw SessionFailure.staleOperation }
        guard !mutating else { throw SessionFailure.busy }
        if try vault.pending() != nil { throw SessionFailure.pendingSignOut }
        let epoch = vault.epoch()
        try vault.check(epoch)
        var components = URLComponents(url: configuration.argusAPIURL.appending(path: "api/v1/" + route + path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        request.httpBody = body
        if body != nil { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        for (name, value) in headers { request.setValue(value, forHTTPHeaderField: name) }
        if let key { request.setValue(key, forHTTPHeaderField: "Idempotency-Key") }
        return try await authenticatedResponse(using: activeAuth(), epoch: epoch, request: request).0
    }
}
