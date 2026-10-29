import Combine
import Foundation
import ArgusSession

/// Client switches for the invites surface. This is the only place that reads them.
struct InvitationFlags: Equatable {
    /// Off: the app never asks `/invites/access`, shows no gate and no Invitations row.
    var surface = false
    /// Off: no invitation link of any scheme is handled.
    var links = false

    static func load(bundle: Bundle = .main) -> InvitationFlags {
        func on(_ key: String) -> Bool {
            let value = bundle.object(forInfoDictionaryKey: key)
            return value as? Bool == true || (value as? String)?.lowercased() == "true"
        }
        return InvitationFlags(surface: on("CUADRAO_BETA_INVITES_ENABLED"), links: on("CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED"))
    }
}

/// Where the server sends people for the waitlist and for TestFlight.
struct InviteDestinations: Equatable {
    let waitlist: URL?
    let testFlight: URL?
}

/// Beta admission. `required` and `admitted` exist only as the server's answer.
enum Admission: Equatable {
    /// The invites surface is off in this build or on this server: today's app.
    case off
    case checking
    /// The first check got no answer. The app stays closed until one arrives.
    case unanswered
    case required(InviteDestinations)
    case admitted(InviteDestinations)

    var destinations: InviteDestinations? {
        switch self {
        case .required(let value), .admitted(let value): value
        case .off, .checking, .unanswered: nil
        }
    }
    var isAnswered: Bool { self != .checking && self != .unanswered }

    mutating func answered(_ access: BetaAccess) {
        let destinations = InviteDestinations(waitlist: access.waitlistURL, testFlight: access.testFlightURL)
        self = access.admitted ? .admitted(destinations) : .required(destinations)
    }
    /// A read that got no answer never replaces an answer.
    mutating func failed(_ problem: InvitationProblem) {
        if problem == .surfaceUnavailable { self = .off } else if self == .checking { self = .unanswered }
    }
}

/// A server list. A failed reload keeps the last answer.
enum Loaded<Value: Equatable>: Equatable {
    case loading, failed, ready(Value)
    var value: Value? { if case .ready(let value) = self { value } else { nil } }
    mutating func fail() { if value == nil { self = .failed } }
}

enum FounderLinks: Equatable { case notFounder, links([GroupLink]) }

enum InvitationGate: Equatable { case ready, checking, problem(InvitationProblem) }

enum GroupLinkCreation: Equatable {
    case draft, creating
    /// The one-time secrets stay here until the founder starts another link.
    case created(CreatedInvite, used: Int)
}

/// Beta admission and the invitations a person sends. Household membership stays with
/// `HouseholdModel` and account access with its grants; nothing here infers either one.
@MainActor
final class InvitationsModel: ObservableObject {
    enum Notice: Identifiable, Equatable {
        case alreadyAdmitted, secretsShownOnce, householdUnavailable
        case groupLink(GroupLinkDraft.Invalid)
        case problem(InvitationProblem)
        var id: String { String(describing: self) }
    }

    @Published private(set) var identity: SessionSnapshot?
    @Published private(set) var admission: Admission
    @Published private(set) var gate = InvitationGate.ready
    @Published var gateCode = ""
    /// A link opened before the person could act on it. Taken exactly once, by `routeLink`.
    @Published private(set) var pendingLink: InviteSecret?
    @Published var notice: Notice?
    @Published private(set) var personal = Loaded<SentInvites>.loading
    @Published private(set) var creatingPersonal = false
    @Published private(set) var createdPersonal: CreatedInvite?
    @Published private(set) var groupLinks = Loaded<FounderLinks>.loading
    @Published private(set) var group = GroupLinkCreation.draft

    let flags: InvitationFlags
    var openHousehold: ((String) async -> Bool)?
    private let clientFor: (SessionSnapshot) -> InvitesClient
    private var generation = UUID()
    private var accessIssued = 0
    private var accessApplied = 0
    private var createKey: UUID?
    private var groupAttempt: (draft: GroupLinkDraft, key: UUID)?

    init(flags: InvitationFlags, clientFor: @escaping (SessionSnapshot) -> InvitesClient) {
        self.flags = flags
        self.clientFor = clientFor
        admission = flags.surface ? .checking : .off
    }

    var showsInvitations: Bool { if case .admitted = admission { true } else { false } }

    func bind(_ next: SessionSnapshot?) {
        let signedIn = next?.phase == .authenticated ? next : nil
        guard signedIn?.revision != identity?.revision || signedIn?.profile?.id != identity?.profile?.id else { return }
        // A link belongs to the person who opened it; it waits for sign-in and ends with the session.
        if identity != nil { pendingLink = nil }
        identity = signedIn; generation = UUID()
        admission = flags.surface ? .checking : .off
        gate = .ready; gateCode = ""; notice = nil
        personal = .loading; creatingPersonal = false; createdPersonal = nil; groupLinks = .loading; group = .draft
        createKey = nil; groupAttempt = nil
    }

    // MARK: Beta admission

    func refreshAccess() async {
        guard flags.surface, let identity else { await routeLink(); return }
        let ticket = generation
        accessIssued += 1
        let order = accessIssued
        do {
            let value = try await clientFor(identity).access()
            guard ticket == generation, order > accessApplied else { return }
            accessApplied = order
            admission.answered(value)
        } catch {
            guard ticket == generation, order > accessApplied else { return }
            admission.failed(InvitationProblem(error))
        }
        await routeLink()
    }

    func retryAccess() async {
        if admission == .unanswered { admission = .checking }
        await refreshAccess()
    }

    func submitCode(_ input: String) async {
        guard let identity, case .required(let destinations) = admission, gate != .checking else { return }
        guard let secret = InviteSecret(input: input) else { gate = .problem(.invalid); return }
        let ticket = generation
        gate = .checking
        do {
            let result = try await clientFor(identity).redeem(secret)
            guard ticket == generation else { return }
            gateCode = ""; gate = .ready
            if result.admitted {
                // The redeem answer outranks any access read that started before it.
                accessIssued += 1; accessApplied = accessIssued
                admission = .admitted(destinations)
            }
            await refreshAccess()
        } catch {
            guard ticket == generation else { return }
            switch InvitationProblem(error) {
            case .householdInvitation:
                gate = .ready
                await handToHousehold(secret)
            case .surfaceUnavailable:
                gate = .ready; admission = .off
            case let problem:
                gate = .problem(problem)
            }
        }
    }

    // MARK: Links

    /// Keeps a link until the person is signed in and the server has answered. Returns false when unhandled.
    @discardableResult
    func open(_ url: URL) async -> Bool {
        guard flags.links, let token = InvitationLink.token(in: url) else { return false }
        pendingLink = .token(token)
        await routeLink()
        return true
    }

    func discardPendingLink() { pendingLink = nil }

    /// Takes the link and puts it in front of the person. Nothing here redeems or accepts.
    private func routeLink() async {
        guard let identity, admission.isAnswered, let secret = pendingLink else { return }
        pendingLink = nil
        switch admission {
        case .checking, .unanswered:
            return
        case .required:
            gateCode = Self.text(secret); if gate != .checking { gate = .ready }
        case .off:
            await handToHousehold(secret)
        case .admitted:
            let ticket = generation
            do {
                let preview = try await clientFor(identity).preview(secret)
                guard ticket == generation else { return }
                if preview.kind == .household { await handToHousehold(secret) } else { notice = .alreadyAdmitted }
            } catch {
                guard ticket == generation else { return }
                let problem = InvitationProblem(error)
                if problem == .surfaceUnavailable { await handToHousehold(secret) } else { notice = .problem(problem) }
            }
        }
    }

    private func handToHousehold(_ secret: InviteSecret) async {
        if await openHousehold?(Self.text(secret)) != true { notice = .householdUnavailable }
    }

    private static func text(_ secret: InviteSecret) -> String {
        switch secret { case .token(let value), .code(let value): value }
    }

    // MARK: Personal invitations

    func loadPersonal() async {
        guard let identity else { return }
        let ticket = generation
        do {
            let value = try await clientFor(identity).sent()
            guard ticket == generation else { return }
            personal = .ready(value)
        } catch {
            guard ticket == generation else { return }
            personal.fail()
        }
    }

    func createPersonal() async {
        guard let identity, !creatingPersonal else { return }
        let ticket = generation
        let key = createKey ?? UUID()
        createKey = key
        creatingPersonal = true
        do {
            let value = try await clientFor(identity).createInvite(key: key)
            guard ticket == generation else { return }
            createKey = nil
            if value.invitation.hasSecrets { createdPersonal = value.invitation } else { notice = .secretsShownOnce }
            if let quota = value.quota, let sent = personal.value { personal = .ready(SentInvites(quota: quota, invitations: sent.invitations)) }
        } catch {
            guard ticket == generation else { return }
            let problem = InvitationProblem(error)
            // No answer means the create may have committed: the same key asks again.
            if problem != .unavailable { createKey = nil }
            if problem != .quotaExhausted { notice = .problem(problem) }
        }
        creatingPersonal = false
        await loadPersonal()
    }

    // MARK: Founder group links

    func loadGroupLinks() async {
        guard let identity else { return }
        let ticket = generation
        do {
            let links = try await clientFor(identity).groupLinks()
            guard ticket == generation else { return }
            groupLinks = .ready(.links(links))
            if case .created(let invite, _) = group, let link = links.first(where: { $0.id == invite.id }) {
                group = .created(invite, used: link.redeemed)
            }
        } catch {
            guard ticket == generation else { return }
            if InvitationProblem(error) == .founderOnly { groupLinks = .ready(.notFounder) } else { groupLinks.fail() }
        }
    }

    func startGroupLink() { if case .created = group { group = .draft } }

    func createGroupLink(label: String, cap: Int, expiresAt: Date) async {
        guard let identity, group != .creating else { return }
        let draft: GroupLinkDraft
        do { draft = try GroupLinkDraft(label: label, cap: cap, expiresAt: expiresAt) }
        catch { notice = .groupLink(error as? GroupLinkDraft.Invalid ?? .label); return }
        let ticket = generation
        // The server ties a key to one request body, so a changed draft takes a new key.
        let key = groupAttempt?.draft == draft ? groupAttempt?.key ?? UUID() : UUID()
        groupAttempt = (draft, key)
        group = .creating
        do {
            let value = try await clientFor(identity).createGroupLink(draft, key: key)
            guard ticket == generation else { return }
            groupAttempt = nil
            if value.invitation.hasSecrets {
                group = .created(value.invitation, used: 0)
            } else {
                group = .draft; notice = .secretsShownOnce
            }
        } catch {
            guard ticket == generation else { return }
            let problem = InvitationProblem(error)
            if problem != .unavailable { groupAttempt = nil }
            group = .draft; notice = .problem(problem == .invalid ? .refused : problem)
        }
        await loadGroupLinks()
    }

    func revokeGroupLink(_ id: UUID) async {
        guard let identity else { return }
        let ticket = generation
        do { try await clientFor(identity).revokeGroupLink(id) }
        catch { if ticket == generation { notice = .problem(InvitationProblem(error)) } }
        await loadGroupLinks()
    }
}
