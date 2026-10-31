import Foundation
import XCTest
@testable import ArgusSession

/// Answers like `/api/v1/invites` in docs/api/openapi.yaml and records each request.
actor InvitesWire: InvitesTransport {
    struct Sent: Equatable { let route: String; let path: String; let method: String; let body: [String: String]; let key: String? }
    private(set) var sent: [Sent] = []
    private var replies: [String: Result<[String: Any], SessionFailure>] = [:]

    func reply(_ path: String, _ json: [String: Any]) { replies[path] = .success(json) }
    func fail(_ path: String, status: Int, code: String?) { replies[path] = .failure(.rejected(status: status, code: code)) }
    func requests() -> [Sent] { sent }

    func send(route: String, path: String, method: String, body: Data?, key: String?) async throws -> Data {
        let fields = body.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?.mapValues { "\($0)" } ?? [:]
        sent.append(Sent(route: route, path: path, method: method, body: fields, key: key))
        switch replies[path] {
        case .success(let json): return try JSONSerialization.data(withJSONObject: json)
        case .failure(let failure): throw failure
        case nil: return Data("{}".utf8)
        }
    }
}

enum InviteWireFixture {
    static let id = "8d0f7a8e-5a35-4f43-9b7f-0d1f1b8f2a11"
    static var quota: [String: Any] { ["limit": 10, "used": 3, "remaining": 7] }
    static func created(secrets: Bool, kind: String = "beta", link: Any = "https://cuadrao.ai/invite#tok3n-value-from-server") -> [String: Any] {
        ["invitation": ["id": id, "kind": kind, "expires_at": "2026-10-10T18:30:00.123456+00:00",
                        "token": secrets ? "tok3n-value-from-server" : NSNull(), "code": secrets ? "7K2M-9QXD-4RTA" : NSNull(),
                        "link": secrets ? link : NSNull(), "source_label": kind == "group_link" ? "Launch dinner" : NSNull(),
                        "cap": kind == "group_link" ? 25 : NSNull(), "replayed": !secrets] as [String: Any],
         "quota": kind == "group_link" ? NSNull() : quota]
    }
}

final class InvitationsTests: XCTestCase {
    func testTypedCodesLinksAndBareTokensBecomeExactlyOneSecret() throws {
        XCTAssertEqual(InviteSecret(input: "  7k2m-9qxd-4rta \n"), .code("7k2m-9qxd-4rta"))
        XCTAssertEqual(InviteSecret(input: "https://cuadrao.ai/invite#abcDEF123_-xyz"), .token("abcDEF123_-xyz"))
        XCTAssertEqual(InviteSecret(input: "argus-household://invite#legacy-token-123"), .token("legacy-token-123"))
        XCTAssertEqual(InviteSecret(input: String(repeating: "t", count: 43)), .token(String(repeating: "t", count: 43)))
        XCTAssertNil(InviteSecret(input: "   "))
        XCTAssertNil(InviteSecret(input: "https://example.com/invite#abc"))
        XCTAssertNil(InviteSecret(input: "https://cuadrao.ai/plans#abc"))
        XCTAssertNil(InviteSecret(input: "https://cuadrao.ai/invite?token=abc"))
        XCTAssertNil(InviteSecret(input: "mailto:someone@example.com"))
        let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(InviteSecret.code("7K2M-9QXD-4RTA"))) as? [String: String]
        XCTAssertEqual(encoded, ["code": "7K2M-9QXD-4RTA"])
        let household = try JSONSerialization.jsonObject(with: JSONEncoder().encode(HouseholdCommand(secret: .token("abc12345"), displayName: "Ana"))) as? [String: String]
        XCTAssertEqual(household, ["token": "abc12345", "display_name": "Ana"])
    }

    func testOnlyTheServersTwoLinkShapesCarryAnInvitation() {
        XCTAssertEqual(InvitationLink.token(in: URL(string: "https://CUADRAO.ai/invite#T0KEN")!), "T0KEN")
        XCTAssertNil(InvitationLink.token(in: URL(string: "https://cuadrao.ai:8443/invite#T0KEN")!))
        XCTAssertNil(InvitationLink.token(in: URL(string: "https://cuadrao.ai.evil.example/invite#T0KEN")!))
        XCTAssertNil(InvitationLink.token(in: URL(string: "http://cuadrao.ai/invite#T0KEN")!))
        XCTAssertNil(InvitationLink.token(in: URL(string: "https://cuadrao.ai/invite")!))
        XCTAssertTrue(InvitationLink.isUniversal(URL(string: "https://cuadrao.ai/invite#T0KEN")!))
        XCTAssertFalse(InvitationLink.isUniversal(URL(string: "argus-household://invite#T0KEN")!))
    }

    func testAccessSentAndCreatedDecodeTheContractShapes() async throws {
        let wire = InvitesWire()
        let client = InvitesClient(transport: wire)
        await wire.reply("/access", ["gate_enabled": true, "admitted": false, "waitlist_url": "https://cuadrao.ai/waitlist", "testflight_url": NSNull()])
        let access = try await client.access()
        XCTAssertEqual(access, BetaAccess(gateEnabled: true, admitted: false, waitlistURL: URL(string: "https://cuadrao.ai/waitlist"), testFlightURL: nil))

        await wire.reply("", ["quota": InviteWireFixture.quota, "invitations": [
            ["id": InviteWireFixture.id, "kind": "beta", "invitation_id": InviteWireFixture.id, "state": "accepted",
             "sent_at": "2026-10-03T10:00:00+00:00", "expires_at": "2026-10-10T10:00:00.5+00:00", "accepted_at": "2026-10-04T08:00:00Z"],
            ["id": UUID().uuidString, "kind": "household", "invitation_id": NSNull(), "state": "pending",
             "sent_at": "2026-10-03T10:00:00.000001+00:00", "expires_at": NSNull(), "accepted_at": NSNull()]] as [[String: Any]]])
        let sent = try await client.sent()
        XCTAssertEqual(sent.quota, InviteQuota(limit: 10, used: 3, remaining: 7))
        XCTAssertEqual(sent.invitations.map(\.state), [.accepted, .pending])
        XCTAssertEqual(sent.invitations.map(\.kind), [.beta, .household])
        XCTAssertEqual(sent.invitations[0].acceptedAt, InvitationDates.date("2026-10-04T08:00:00Z"))
        XCTAssertNil(sent.invitations[1].acceptedAt)

        await wire.reply("", InviteWireFixture.created(secrets: true))
        let created = try await client.createInvite(key: UUID())
        XCTAssertEqual(created.invitation.code, "7K2M-9QXD-4RTA")
        XCTAssertEqual(created.invitation.link?.absoluteString, "https://cuadrao.ai/invite#tok3n-value-from-server")
        XCTAssertTrue(created.invitation.hasSecrets)
        XCTAssertEqual(created.quota?.remaining, 7)

        await wire.reply("", InviteWireFixture.created(secrets: true, link: NSNull()))
        let codeOnly = try await client.createInvite(key: UUID())
        XCTAssertNil(codeOnly.invitation.link)
        XCTAssertTrue(codeOnly.invitation.hasSecrets)

        await wire.reply("", InviteWireFixture.created(secrets: false))
        let replayed = try await client.createInvite(key: UUID())
        XCTAssertTrue(replayed.invitation.replayed)
        XCTAssertFalse(replayed.invitation.hasSecrets)
    }

    func testPreviewRedeemAndGroupLinksDecodeTheContractShapes() async throws {
        let wire = InvitesWire()
        let client = InvitesClient(transport: wire)
        await wire.reply("/preview", ["kind": "household", "available": true, "expires_at": "2026-10-10T00:00:00+00:00", "household_name": "Casa"])
        let preview = try await client.preview(.code("7K2M-9QXD-4RTA"))
        XCTAssertEqual(preview.kind, .household); XCTAssertEqual(preview.householdName, "Casa"); XCTAssertTrue(preview.available)
        await wire.reply("/redeem", ["admitted": true, "outcome": "already_admitted", "kind": "group_link", "replayed": false])
        let redeemed = try await client.redeem(.token("abcdefgh"))
        XCTAssertEqual(redeemed.outcome, .alreadyAdmitted); XCTAssertEqual(redeemed.kind, .groupLink)
        await wire.reply("/group-links", ["links": [["id": InviteWireFixture.id, "source_label": "Launch dinner", "cap": 25, "redeemed": 25, "overflow": 2,
                                                     "expires_at": "2026-11-01T00:00:00+00:00", "revoked_at": NSNull(), "state": "full"] as [String: Any]]])
        let links = try await client.groupLinks()
        XCTAssertEqual(links.map(\.state), [.full]); XCTAssertEqual(links.first?.overflow, 2)
    }

    func testRequestsCarryOneSecretTheRouteAndAnIdempotencyKeyOnlyForCreates() async throws {
        let wire = InvitesWire()
        let client = InvitesClient(transport: wire)
        let key = UUID()
        await wire.reply("", InviteWireFixture.created(secrets: true))
        _ = try await client.createInvite(key: key)
        _ = try? await client.redeem(.code("7K2M-9QXD-4RTA"))
        _ = try? await client.preview(.token("abcdefgh"))
        await wire.reply("/group-links", InviteWireFixture.created(secrets: true, kind: "group_link"))
        let expiry = try XCTUnwrap(InvitationDates.date("2026-11-01T00:00:00Z"))
        let draft = try GroupLinkDraft(label: " Launch dinner ", cap: 25, expiresAt: expiry, now: expiry.addingTimeInterval(-86_400))
        _ = try await client.createGroupLink(draft, key: key)
        let id = UUID()
        try await client.revokeGroupLink(id)
        let sent = await wire.requests()
        XCTAssertEqual(sent, [
            .init(route: "invites", path: "", method: "POST", body: [:], key: key.uuidString),
            .init(route: "invites", path: "/redeem", method: "POST", body: ["code": "7K2M-9QXD-4RTA"], key: nil),
            .init(route: "invites", path: "/preview", method: "POST", body: ["token": "abcdefgh"], key: nil),
            .init(route: "invites", path: "/group-links", method: "POST", body: ["source_label": "Launch dinner", "cap": "25", "expires_at": "2026-11-01T00:00:00Z"], key: key.uuidString),
            .init(route: "invites", path: "/group-links/" + id.uuidString.lowercased() + "/revoke", method: "POST", body: [:], key: nil),
        ])
    }

    func testEveryProblemCodeBecomesTheOutcomeTheScreensExplain() async throws {
        let cases: [(Int, String?, InvitationProblem)] = [
            (404, "invitation_not_found", .invalid), (422, "validation_error", .invalid),
            (409, "invitation_expired", .expired), (409, "invitation_revoked", .revoked),
            (409, "invitation_consumed", .used), (409, "group_link_full", .full),
            (429, "invite_rate_limited", .rateLimited), (429, nil, .rateLimited),
            (409, "household_invitation_requires_accept", .householdInvitation),
            (409, "beta_invite_quota_exhausted", .quotaExhausted), (403, "founder_required", .founderOnly),
            (403, "beta_invite_required", .invitationRequired), (404, "invites_unavailable", .surfaceUnavailable),
            (422, "invite_request_invalid", .refused), (409, "idempotency_conflict", .refused), (403, "household_admin_required", .refused),
            (400, "idempotency_key_required", .refused), (500, nil, .unavailable),
            (403, "account_conversion_required", .signedOut),
        ]
        for (status, code, expected) in cases {
            let wire = InvitesWire()
            await wire.fail("/redeem", status: status, code: code)
            do {
                _ = try await InvitesClient(transport: wire).redeem(.code("7K2M-9QXD-4RTA"))
                XCTFail("\(status) \(code ?? "nil") must fail")
            } catch {
                XCTAssertEqual(error as? InvitationProblem, expected, "\(status) \(code ?? "nil")")
            }
        }
        XCTAssertEqual(InvitationProblem(SessionFailure.unauthorized), .signedOut)
        XCTAssertEqual(InvitationProblem(SessionFailure.unavailable), .unavailable)
        XCTAssertEqual(InvitationProblem(URLError(.notConnectedToInternet)), .unavailable)
    }

    func testAGroupLinkDraftHoldsTheServersLimits() throws {
        let now = try XCTUnwrap(InvitationDates.date("2026-10-01T00:00:00Z"))
        let week = now.addingTimeInterval(7 * 86_400)
        let draft = try GroupLinkDraft(label: "  Cena  ", cap: 10_000, expiresAt: now.addingTimeInterval(365 * 86_400), now: now)
        XCTAssertEqual(draft.label, "Cena")
        XCTAssertEqual(draft.expires, "2027-10-01T00:00:00Z")
        // The server counts code points: one family emoji is one character but seven scalars.
        let family = "\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}\u{200D}\u{1F466}"
        XCTAssertEqual(family.count, 1)
        let fullest = String(repeating: family, count: 11) + "abc"
        XCTAssertEqual(try GroupLinkDraft(label: fullest, cap: 5, expiresAt: week, now: now).label, fullest)
        let refused: [(String, Int, Date, GroupLinkDraft.Invalid)] = [
            ("   ", 5, week, .label), (String(repeating: "a", count: 81), 5, week, .label),
            (String(repeating: family, count: 12), 5, week, .label),
            ("Cena", 0, week, .cap), ("Cena", 10_001, week, .cap),
            ("Cena", 5, now, .expiry), ("Cena", 5, now.addingTimeInterval(365 * 86_400 + 1), .expiry),
        ]
        for (label, cap, expiry, expected) in refused {
            XCTAssertThrowsError(try GroupLinkDraft(label: label, cap: cap, expiresAt: expiry, now: now)) {
                XCTAssertEqual($0 as? GroupLinkDraft.Invalid, expected)
            }
        }
    }

    func testAMalformedReplyIsUnavailableNotAnAdmission() async throws {
        let wire = InvitesWire()
        await wire.reply("/redeem", ["admitted": true])
        do { _ = try await InvitesClient(transport: wire).redeem(.code("7K2M-9QXD-4RTA")); XCTFail("must not decode") }
        catch { XCTAssertEqual(error as? InvitationProblem, .unavailable) }
    }

    func testTheSessionTransportSendsTheBearerToTheInvitesRoute() async throws {
        let fixture = try SessionFixture()
        let controller = try fixture.controller()
        let identity = try await fixture.login(controller)
        let client = InvitesClient(transport: SessionInvitesTransport(controller: controller, identity: identity))
        do { _ = try await client.redeem(.code("7K2M-9QXD-4RTA")); XCTFail("the fixture server knows no invites") }
        catch { XCTAssertEqual(error as? InvitationProblem, .refused) }
        let captured = await fixture.server.captured()
        let request = try XCTUnwrap(captured.last)
        XCTAssertEqual(request.url?.absoluteString, "https://api.example.test/api/v1/invites/redeem")
        XCTAssertEqual(request.httpMethod, "POST")
        XCTAssertTrue(request.value(forHTTPHeaderField: "Authorization")?.hasPrefix("Bearer ") == true)
        XCTAssertNil(request.value(forHTTPHeaderField: "Idempotency-Key"))
    }
}
