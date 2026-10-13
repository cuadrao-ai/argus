import SwiftUI
import ArgusSession

/// One sheet owner for AccountsModel drafts. Create and rename use the approved Cuadrao sheets;
/// full details and the reviewed starting balance keep AccountForm, which the Preview has no sheet for.
struct ConnectedAccountSheet: View {
    @ObservedObject var model: AccountsModel
    /// Captured at presentation so the dismissal animation keeps the same sheet after the draft clears.
    let mode: AccountDraft.Mode
    @Environment(\.locale) private var locale

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        switch mode {
        case .create: ConnectedAccountCreateSheet(model: model, spanish: spanish)
        case .rename: ConnectedAccountRenameSheet(model: model, spanish: spanish)
        case .metadata, .opening: AccountForm(model: model).tint(ArgusStyle.ink).foregroundStyle(ArgusStyle.ink)
        }
    }
}

private struct ConnectedAccountCreateSheet: View {
    @ObservedObject var model: AccountsModel
    let spanish: Bool
    @State private var entry = CanvasAccountEntry()

    var body: some View {
        CuadraoAccountEntryForm(entry: $entry, spaceTitle: NSLocalizedString("household.personal", comment: ""),
            spanish: spanish, ids: .connected,
            status: status, statusIdentifier: model.errorKey == nil ? "accounts.status" : "accounts.form.error",
            primaryTitle: model.createIsFrozen ? NSLocalizedString("accounts.retry", comment: "") : nil,
            locked: model.busy || model.createIsFrozen, busy: model.busy,
            cancel: { model.discard() }) {
            if !model.createIsFrozen { model.draft?.apply(entry) }
            Task { await model.save(locale: Locale(identifier: "en_US_POSIX")) }
        }
        .interactiveDismissDisabled()
    }

    private var status: String? {
        let lines = [model.errorKey.map { NSLocalizedString($0, comment: "") },
                     model.createIsFrozen ? NSLocalizedString("accounts.create.retry", comment: "") : nil,
                     model.busy ? NSLocalizedString("accounts.saving", comment: "") : nil].compactMap { $0 }
        return lines.isEmpty ? nil : lines.joined(separator: " ")
    }
}

private struct ConnectedAccountRenameSheet: View {
    @ObservedObject var model: AccountsModel
    let spanish: Bool
    @State private var name = ""

    private var placeholder: String {
        model.draft?.base.flatMap { ConnectedAccountPresentation.artwork($0.type)?.title(spanish) } ?? ""
    }

    var body: some View {
        CuadraoRenameAccountForm(name: $name, placeholder: placeholder, spanish: spanish,
            nameIdentifier: "accounts.nickname", saveIdentifier: "accounts.save", cancelIdentifier: "accounts.cancel",
            status: status, statusIdentifier: model.errorKey == nil ? "accounts.status" : "accounts.form.error",
            primaryTitle: primaryTitle, busy: model.busy, cancel: { model.discard() }) {
            if model.needsReview {
                if model.latest == nil { model.discard() } else { model.editLatest() }
            } else {
                model.draft?.nickname = name.trimmingCharacters(in: .whitespacesAndNewlines)
                Task { await model.save() }
            }
        }
        .interactiveDismissDisabled()
        .onAppear {
            guard let base = model.draft?.base else { return }
            name = ConnectedAccountPresentation.title(base, spanish: spanish)
        }
    }

    private var primaryTitle: String? {
        guard model.needsReview else { return nil }
        return NSLocalizedString(model.latest == nil ? "action.close" : "accounts.review.latest", comment: "")
    }

    private var status: String? {
        if model.needsReview {
            return NSLocalizedString(model.latest == nil ? "accounts.review.unavailable" : "accounts.review.required", comment: "")
        }
        if let key = model.errorKey { return NSLocalizedString(key, comment: "") }
        return model.busy ? NSLocalizedString("accounts.saving", comment: "") : nil
    }
}

private extension CanvasAccountEntryIDs {
    static var connected: CanvasAccountEntryIDs {
        CanvasAccountEntryIDs(type: { "accounts.type." + ConnectedAccountPresentation.type($0) },
            typeChange: "accounts.type.change", otherAssets: "accounts.otherAssets", name: "accounts.nickname",
            amount: "accounts.amount", currency: "accounts.currency", share: "assets.share.change",
            save: "accounts.save", cancel: "accounts.cancel")
    }
}
