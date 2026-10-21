import Foundation

@main struct ReceiptDraftOnlyChecks {
    static func main() throws {
        var count = 0
        func check(_ value: @autoclosure () -> Bool, _ message: String) {
            precondition(value(), message)
            count += 1
        }
        func postingBlocked(_ operation: () throws -> Void) throws {
            do {
                try operation()
                preconditionFailure("Draft-only storage must reject posting")
            } catch ReceiptPostingCapability.Failure.unavailable {
                count += 1
            }
        }

        let support = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: support) }
        let owner = UUID()
        let store = CuadraoReceiptStore.connectedDrafts(userID: owner, applicationSupport: support)
        let otherOwner = CuadraoReceiptStore.connectedDrafts(userID: UUID(), applicationSupport: support)
        let preview = CuadraoReceiptStore(directory: support.appendingPathComponent("CuadraoReceipts"))
        let source = Data("Source retained by the native capture adapter".utf8)
        let origin = ReceiptOrigin(groupID: nil, threadID: UUID().uuidString)
        let previewID = try preview.capture(files: [(source, "preview.jpg", false)], currency: nil,
            origin: origin, group: nil, example: false, spanish: false)
        let id = try store.capture(files: [(source, "original.pdf", true)], currency: nil,
            origin: origin, group: nil, example: false, spanish: false)
        var draft = store.receipt(id)!
        check(!store.postingCapability.allowsPosting, "Connected factory always creates a draft-only store")
        check(preview.postingCapability.allowsPosting, "Default Preview posting remains available")
        check(draft.currency == nil && draft.lines.isEmpty, "Saving a connected source invents no receipt details")
        draft.merchant = "Reviewed merchant"
        try store.update(draft)
        let reopened = CuadraoReceiptStore.connectedDrafts(userID: owner, applicationSupport: support)
        check(reopened.receipt(id) == store.receipt(id), "Draft edits survive reopening the authenticated store")
        let retained = try Data(contentsOf: reopened.url(reopened.receipt(id)!.source[0]))
        check(retained == source, "The original source survives Later and relaunch")
        check(otherOwner.receipts.isEmpty && otherOwner.directory != store.directory,
              "Another authenticated identity never reads this person's drafts")
        check(preview.receipt(id) == nil && reopened.receipt(previewID) == nil && preview.directory != store.directory,
              "Connected drafts and Preview receipts remain in separate directories")

        // Populated dependencies prove that the store gate does not rely on the wrapper's empty pickers.
        let accounts = CuadraoAccountsPreview(populated: true, spanish: false)
        let groups = CuadraoGroupPreview(spanish: false, defaults: nil)
        let account = accounts.accounts.first!
        let group = groups.groups.first!
        let balances = accounts.accounts.map(\.balance)
        let activity = accounts.activity.map(\.id)
        let originalGroups = groups.groups
        var groupReceiptID: UUID?
        for destination in [ReceiptDestination.personal(accountID: account.id), .group(group.id)] {
            let isGroup: Bool
            switch destination { case .group: isGroup = true; case .personal: isGroup = false }
            let target = isGroup ? group : nil
            let receiptID = try store.capture(files: [(source, "review.jpg", false)], currency: account.currency,
                origin: .init(groupID: target?.id, threadID: origin.threadID), group: target,
                example: true, spanish: false)
            var ready = store.receipt(receiptID)!
            ready.destination = destination
            try ready.validate()
            try store.update(ready)
            let before = store.receipt(receiptID)
            try postingBlocked { try store.confirm(receiptID, groups: groups, accounts: accounts) }
            check(store.receipt(receiptID) == before, "Blocked confirmation preserves the complete draft")
            if isGroup { groupReceiptID = receiptID }
        }
        check(accounts.activity.map(\.id) == activity && accounts.accounts.map(\.balance) == balances,
              "Blocked personal confirmation changes no activity or balance")
        check(groups.groups == originalGroups, "Blocked group confirmation adds no expense")

        let interrupted = store.receipt(groupReceiptID!)!
        try groups.confirmReceipt(interrupted, groupID: group.id)
        try postingBlocked { try store.reconcile(groups: groups, accounts: accounts) }
        check(store.receipt(interrupted.id) == interrupted, "Draft-only reconciliation cannot confirm a receipt")

        let confirmedID = try preview.capture(files: [(source, "confirmed.jpg", false)], currency: account.currency,
            origin: origin, group: nil, example: true, spanish: false)
        var confirmed = preview.receipt(confirmedID)!
        confirmed.destination = .personal(accountID: account.id)
        try preview.update(confirmed)
        try preview.confirm(confirmedID, groups: groups, accounts: accounts)
        let projectionTarget = CuadraoAccountsPreview(populated: false, spanish: false)
        projectionTarget.accounts = [account]
        let restricted = CuadraoReceiptStore(directory: preview.directory, postingCapability: .draftOnly)
        check(restricted.receipt(confirmedID)?.prepared == false, "Projection test loads an actually confirmed receipt")
        restricted.projectPersonal(into: projectionTarget)
        check(projectionTarget.activity.isEmpty && projectionTarget.account(account.id)?.balance == account.balance,
              "Draft-only projection cannot create personal activity or alter a balance")

        let originalURL = store.url(store.receipt(id)!.source[0])
        try store.discard(id, groups: groups)
        check(store.receipt(id) == nil && !FileManager.default.fileExists(atPath: originalURL.path),
              "Discard still removes a connected draft and its source")
        check(CuadraoReceiptStore.connectedDrafts(userID: owner, applicationSupport: support).receipt(id) == nil,
              "Discard remains durable when the person returns")

        let deletedOwner = UUID()
        let remainingOwner = UUID()
        let deleted = CuadraoReceiptStore.connectedDrafts(userID: deletedOwner, applicationSupport: support)
        let remaining = CuadraoReceiptStore.connectedDrafts(userID: remainingOwner, applicationSupport: support)
        let deletedID = try deleted.capture(files: [(source, "deleted.pdf", true)], currency: nil,
            origin: origin, group: nil, example: false, spanish: false)
        let remainingID = try remaining.capture(files: [(source, "remaining.pdf", true)], currency: nil,
            origin: origin, group: nil, example: false, spanish: false)
        let deletedSource = deleted.url(deleted.receipt(deletedID)!.source[0])
        let guestBook = support.appendingPathComponent("CuadraoDeviceBook", isDirectory: true)
        let guestReceipt = guestBook.appendingPathComponent("receipts", isDirectory: true).appendingPathComponent("receipts.json")
        try FileManager.default.createDirectory(at: guestReceipt.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("synthetic guest book".utf8).write(to: guestBook.appendingPathComponent("book.json"))
        try Data("[]".utf8).write(to: guestReceipt)
        try CuadraoReceiptStore.removeConnectedDrafts(userID: deletedOwner, applicationSupport: support)
        check(CuadraoReceiptStore.connectedDrafts(userID: deletedOwner, applicationSupport: support).receipts.isEmpty
              && !FileManager.default.fileExists(atPath: deletedSource.path),
              "Account-deletion cleanup removes that person's drafts and their sources")
        check((try? String(contentsOf: guestBook.appendingPathComponent("book.json"), encoding: .utf8)) == "synthetic guest book"
              && (try? String(contentsOf: guestReceipt, encoding: .utf8)) == "[]",
              "The guest book and its receipts survive an account's cleanup")
        let survivor = CuadraoReceiptStore.connectedDrafts(userID: remainingOwner, applicationSupport: support)
        check(survivor.receipt(remainingID)?.source.first?.name == "remaining.pdf"
              && (try? Data(contentsOf: survivor.url(survivor.receipt(remainingID)!.source[0]))) == source,
              "Another identity's drafts and sources survive the cleanup")
        try CuadraoReceiptStore.removeConnectedDrafts(userID: deletedOwner, applicationSupport: support)
        try CuadraoReceiptStore.removeConnectedDrafts(userID: UUID(), applicationSupport: support)
        check(CuadraoReceiptStore.connectedDrafts(userID: remainingOwner, applicationSupport: support).receipts.map(\.id) == [remainingID],
              "Repeating cleanup or cleaning an owner with no drafts succeeds without effects")
        print("Receipt draft-only checks passed: \(count)")
    }
}
