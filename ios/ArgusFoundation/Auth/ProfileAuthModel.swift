import SwiftUI
import ArgusSession

@MainActor
final class ProfileAuthModel: ObservableObject {
    enum State { case accountDeletionUncertain, accountDeletionPending, disabled, configurationInvalid, signedOut, authenticated, pendingSignOut, unsupportedAnonymous, credentialValidationRequired, reauthenticationRequired }
    @Published private(set) var state: State = .disabled
    @Published private(set) var busy = false
    /// True once the first launch restore has finished, so a host can wait for it before choosing what to show.
    @Published private(set) var hasRestored = false
    @Published private(set) var profile: SessionProfile?
    @Published private(set) var confirmationRequired = false
    @Published private(set) var errorKey: String?
    @Published private(set) var appleNameSave: AppleNameSaveOutcome?
    @Published private(set) var appleCapture: AppleCaptureOutcome?
    @Published var captureNoticePresented = false
    @Published private(set) var accounts: AccountsModel?
    @Published private(set) var financialLoop: FinancialLoopModel?
    @Published private(set) var household: HouseholdModel?
    @Published private(set) var invitations: InvitationsModel?
    @Published private(set) var financialSearch: FinancialSearchModel?
    @Published private(set) var savedReceipts: SavedReceiptsModel?
    @Published private(set) var deletion: AccountDeletionModel?
    let configuration: NativeAuthConfiguration?
    /// Native Apple and Google buttons; `.off` unless email auth is configured too.
    let providers: NativeProviderConfiguration
    private let controller: SessionController?
    private var started = false
    private var revalidationRequested = false
    private var captureNoticeAwaitingSession = false

    convenience init() {
        var loadedConfiguration: NativeAuthConfiguration?
        var loadedController: SessionController?
        // A Release build without auth configuration reports it; it never falls back to the sample shell.
        var initialState = CuadraoFirstRelease.hidesUnfinished ? State.configurationInvalid : State.disabled
        do {
            loadedConfiguration = try NativeAuthConfiguration.load()
            if let loadedConfiguration {
                loadedController = try SessionController(configuration: loadedConfiguration.session, appleChecker: NativeAppleCredentialChecker())
                initialState = .signedOut
            }
        } catch {
            loadedConfiguration = nil
            initialState = .configurationInvalid
        }
        self.init(configuration: loadedConfiguration, controller: loadedController,
                  providers: loadedController == nil ? .off : NativeProviderConfiguration.load(), initialState: initialState)
    }

    init(configuration loadedConfiguration: NativeAuthConfiguration?, controller loadedController: SessionController?,
         providers: NativeProviderConfiguration = .off, initialState: State = .signedOut) {
        configuration = loadedConfiguration
        controller = loadedController
        self.providers = providers
        state = initialState
        if let loadedController {
            deletion = AccountDeletionModel(controller: loadedController, appleAvailable: providers.apple,
                                            cleanup: { try CuadraoReceiptStore.removeConnectedDrafts(userID: $0) })
            deletion?.sessionChanged = { [weak self] snapshot in self?.accept(snapshot) }
            financialSearch = FinancialSearchModel(controller: loadedController, prefix: (loadedConfiguration?.session.storagePrefix ?? "") + ".search.")
            financialSearch?.sessionChanged = { [weak self] snapshot in self?.accept(snapshot) }
            accounts = AccountsModel(controller: loadedController)
            #if DEBUG
            if CuadraoFirstRelease.savedReceiptsSample {
                savedReceipts = SavedReceiptsModel(transport: SampleSavedReceiptsTransport(), currentSession: { await loadedController.snapshot() })
            } else {
                savedReceipts = SavedReceiptsModel(controller: loadedController)
            }
            #else
            savedReceipts = SavedReceiptsModel(controller: loadedController)
            #endif
            savedReceipts?.sessionChanged = { [weak self] snapshot in self?.accept(snapshot) }
            accounts?.financialChanged = { [weak self] in self?.financialSearch?.invalidate() }
            accounts?.sessionChanged = { [weak self] snapshot in self?.accept(snapshot) }
            if let accounts, let loadedConfiguration {
                household = HouseholdModel(controller: loadedController, configuration: loadedConfiguration.session)
                invitations = InvitationsModel(flags: .load()) {
                    InvitesClient(transport: SessionInvitesTransport(controller: loadedController, identity: $0))
                }
                household?.sessionChanged = { [weak self] snapshot in self?.accept(snapshot) }
                financialLoop = FinancialLoopModel(controller: loadedController, accounts: accounts,
                    journal: FinancialWriteJournal(configuration: loadedConfiguration.session))
                financialLoop?.financialChanged = { [weak self] in self?.financialSearch?.invalidate() }
                financialLoop?.sessionChanged = { [weak self] snapshot in self?.accept(snapshot) }
                household?.financialChanged = { [weak self] in
                    await self?.accounts?.load()
                    await self?.financialLoop?.refresh()
                    self?.financialSearch?.invalidate()
                }
            }
        }
    }

    var enabled: Bool { state != .disabled }

    func start() async {
        guard !started else { return }
        started = true
        await restore()
        hasRestored = true
        await deletion?.load()
    }

    func restore() async {
        guard let controller else { return }
        do {
            accept(try await controller.requestCredentialRevalidation())
        } catch {
            accept(await controller.snapshot())
            errorKey = Self.messageKey(error)
        }
        revalidationRequested = true
        guard !busy else { return }
        busy = true
        defer { busy = false }
        repeat {
            revalidationRequested = false
            errorKey = nil
            do {
                accept(try await controller.restore { [weak self] snapshot in await self?.accept(snapshot) })
            } catch {
                accept(await controller.snapshot())
                errorKey = Self.messageKey(error)
            }
        } while revalidationRequested
    }

    private func finishOperation() {
        busy = false
        if revalidationRequested { Task { await restore() } }
    }

    func authenticate(email: String, password: String, captchaToken: String, signup: Bool, language: String, displayName: String) async {
        guard let controller, !busy, state == .signedOut else { return }
        busy = true
        errorKey = nil
        confirmationRequired = false
        defer { finishOperation() }
        do {
            if signup {
                let outcome = try await controller.signup(email: email, password: password, captchaToken: captchaToken,
                                                          language: language, displayName: displayName.isEmpty ? nil : displayName)
                switch outcome {
                case .confirmationRequired:
                    confirmationRequired = true
                    accept(await controller.snapshot())
                case .authenticated(let snapshot): accept(snapshot)
                }
            } else {
                accept(try await controller.login(email: email, password: password, captchaToken: captchaToken))
            }
        } catch {
            accept(await controller.snapshot())
            errorKey = Self.messageKey(error)
        }
    }

    /// Native Apple or Google sign-in through Supabase's id_token grant. Lands in the same
    /// session path as email sign-in. Returns false on failure (errorKey is set).
    @discardableResult
    func signIn(with credential: IdentityTokenCredential, appleAuthorizationCode: String? = nil,
                appleNameAuthorization: AppleNameAuthorization? = nil) async -> Bool {
        guard let controller, !busy, state == .signedOut else { return false }
        busy = true
        errorKey = nil
        confirmationRequired = false
        defer { finishOperation() }
        do {
            let outcome = try await controller.signIn(with: credential, appleAuthorizationCode: appleAuthorizationCode, appleNameAuthorization: appleNameAuthorization)
            accept(outcome.session)
            appleNameSave = outcome.appleName
            appleCapture = outcome.appleCapture
            captureNoticeAwaitingSession = state != .authenticated && captureNoticeKey != nil
            captureNoticePresented = state == .authenticated && captureNoticeKey != nil
            return true
        } catch {
            accept(await controller.snapshot())
            errorKey = Self.messageKey(error)
            return false
        }
    }

    func retryAppleNameSave() async {
        guard let controller, state == .authenticated else { return }
        let identity = await controller.snapshot()
        await perform { try await controller.retryAppleNameInitialization(expectedIdentity: identity) }
    }

    func prepareAppleName(displayName: String?, subject: String) throws -> AppleNameAuthorization {
        guard let controller, !busy, state == .signedOut else { throw SessionFailure.staleOperation }
        return try controller.prepareAppleName(displayName: displayName, subject: subject)
    }

    var captureNoticeKey: String? {
        switch appleCapture {
        case .freshAuthorizationRequired: "auth.apple.capture.fresh"
        case .failed: "auth.apple.capture.failed"
        case .saved, .none: nil
        }
    }

    func dismissCaptureNotice() {
        captureNoticePresented = false
        captureNoticeAwaitingSession = false
        appleCapture = nil
    }

    func setPrimaryCurrency(_ currency: String) async {
        guard let controller, state == .authenticated else { return }
        let identity = await controller.snapshot()
        await perform { try await controller.setPrimaryCurrency(currency, expectedIdentity: identity) }
    }

    /// True only when the profile the server returns carries both names.
    func setNames(displayName: String, preferredName: String) async -> Bool {
        guard let controller, state == .authenticated, !busy else { return false }
        let identity = await controller.snapshot()
        await perform { try await controller.setNames(displayName: displayName, preferredName: preferredName, expectedIdentity: identity) }
        return profile?.displayName == displayName && (profile?.preferredName ?? "") == preferredName
    }

    func signOut() async {
        guard let controller else { return }
        household?.bind(nil)
        financialSearch?.bind(nil)
        savedReceipts?.bind(nil)
        accounts?.bind(nil)
        financialLoop?.bind(nil)
        await perform { try await controller.signOut() }
        await deletion?.load()
    }

    func retryPendingSignOut() async {
        guard let controller else { return }
        await perform { try await controller.retryPendingSignOut() }
    }

    func returnToSignIn() {
        confirmationRequired = false
        errorKey = nil
    }

    func presentationError(_ key: String) { errorKey = key }

    private func perform(_ action: () async throws -> SessionSnapshot) async {
        guard !busy else { return }
        busy = true
        errorKey = nil
        defer { finishOperation() }
        do { accept(try await action()) }
        catch {
            if let controller { accept(await controller.snapshot()) }
            errorKey = Self.messageKey(error)
        }
    }

    private func accept(_ snapshot: SessionSnapshot) {
        if snapshot.phase != .authenticated { captureNoticePresented = false }
        household?.bind(snapshot)
        invitations?.bind(snapshot)
        financialSearch?.bind(snapshot)
        savedReceipts?.bind(snapshot)
        accounts?.bind(snapshot)
        financialLoop?.bind(snapshot)
        profile = snapshot.profile
        switch snapshot.phase {
        case .accountDeletionUncertain: state = .accountDeletionUncertain; dismissCaptureNotice()
        case .accountDeletionPending: state = .accountDeletionPending; dismissCaptureNotice()
        case .signedOut: state = .signedOut; appleNameSave = nil; dismissCaptureNotice()
        case .authenticated:
            if captureNoticeAwaitingSession {
                captureNoticePresented = true
                captureNoticeAwaitingSession = false
            }
            state = .authenticated
        case .signOutPending: state = .pendingSignOut
        case .unsupportedAnonymousSession: state = .unsupportedAnonymous
        case .credentialValidationRequired: state = .credentialValidationRequired
        case .reauthenticationRequired: state = .reauthenticationRequired
        }
    }

    private static func messageKey(_ error: Error) -> String {
        guard let failure = error as? SessionFailure else { return "auth.error.unavailable" }
        switch failure {
        case .unauthorized: return "auth.error.unauthorized"
        case .storageUnavailable: return "auth.error.storage"
        case .pendingSignOut: return "auth.error.pending"
        case .unsupportedAnonymousTransfer: return "auth.error.anonymous"
        case .invalidConfiguration: return "auth.error.configuration"
        case .rejected(let status, _):
            if status >= 500 { return "auth.error.unavailable" }
            return status == 429 ? "auth.error.rateLimit" : "auth.error.rejected"
        default: return "auth.error.unavailable"
        }
    }
}
