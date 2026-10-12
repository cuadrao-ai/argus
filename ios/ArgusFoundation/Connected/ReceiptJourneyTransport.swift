import Foundation
import ArgusSession

/// The server calls the receipt journey needs. The real one talks to the API; tests stub it.
protocol ReceiptJourneyTransport: Sendable {
    func upload(_ bytes: Data, mediaType: String, filename: String, consent: Bool, identity: SessionSnapshot) async throws -> SavedDocumentCapture
    func document(_ connectionID: String, identity: SessionSnapshot) async throws -> FinancialDocumentDetail
    func prepare(_ connectionID: String, identity: SessionSnapshot) async throws -> SavedDocumentCapture
    func openImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent]
    func acceptedImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent]
    func resolve(_ event: FinancialImportEvent, changes: FinancialImportChanges, identity: SessionSnapshot) async throws -> FinancialImportEvent
    func preview(_ eventID: String, identity: SessionSnapshot) async throws -> FinancialImportPreview
    func accept(_ event: FinancialImportEvent, request: FinancialActivityCommand, key: UUID, identity: SessionSnapshot) async throws -> FinancialImportAcceptance
    func link(_ event: FinancialImportEvent, activityID: UUID, identity: SessionSnapshot) async throws -> FinancialImportEvent
    func options(identity: SessionSnapshot) async throws -> FinancialActivityOptions
    func source(_ connectionID: String, identity: SessionSnapshot) async throws -> Data
}

struct SessionReceiptJourneyTransport: ReceiptJourneyTransport {
    let controller: SessionController
    func upload(_ bytes: Data, mediaType: String, filename: String, consent: Bool, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        try await controller.saveDocument(bytes, mediaType: mediaType, filename: filename, consent: consent, expectedIdentity: identity)
    }
    func document(_ connectionID: String, identity: SessionSnapshot) async throws -> FinancialDocumentDetail {
        try await controller.financialDocument(connectionID, expectedIdentity: identity)
    }
    func prepare(_ connectionID: String, identity: SessionSnapshot) async throws -> SavedDocumentCapture {
        try await controller.prepareDocument(connectionID, expectedIdentity: identity)
    }
    func openImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent] {
        try await controller.financialImports(state: "open", expectedIdentity: identity)
    }
    func acceptedImports(identity: SessionSnapshot) async throws -> [FinancialImportEvent] {
        try await controller.financialImports(state: "accepted", expectedIdentity: identity)
    }
    func resolve(_ event: FinancialImportEvent, changes: FinancialImportChanges, identity: SessionSnapshot) async throws -> FinancialImportEvent {
        try await controller.resolveFinancialImport(event, changes: changes, expectedIdentity: identity)
    }
    func preview(_ eventID: String, identity: SessionSnapshot) async throws -> FinancialImportPreview {
        try await controller.previewFinancialImport(eventID, expectedIdentity: identity)
    }
    func accept(_ event: FinancialImportEvent, request: FinancialActivityCommand, key: UUID, identity: SessionSnapshot) async throws -> FinancialImportAcceptance {
        try await controller.acceptFinancialImport(event, request: request, key: key, expectedIdentity: identity)
    }
    func link(_ event: FinancialImportEvent, activityID: UUID, identity: SessionSnapshot) async throws -> FinancialImportEvent {
        try await controller.linkFinancialImport(event, activityID: activityID, expectedIdentity: identity)
    }
    func options(identity: SessionSnapshot) async throws -> FinancialActivityOptions {
        try await controller.financialActivityOptions(expectedIdentity: identity)
    }
    func source(_ connectionID: String, identity: SessionSnapshot) async throws -> Data {
        try await controller.savedDocumentSource(connectionID, expectedIdentity: identity)
    }
}
