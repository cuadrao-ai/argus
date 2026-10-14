import SwiftUI

/// What the signed-in profile needs to offer the claim: where the book lives and how to delete it.
struct GuestClaimEntry {
    let directory: URL
    let discard: () async -> Bool
}

private struct GuestClaimEntryKey: EnvironmentKey {
    static let defaultValue: GuestClaimEntry? = nil
}

extension EnvironmentValues {
    /// Set only while the claim is switched on, an account is signed in and the iPhone still holds a guest book.
    var cuadraoGuestClaim: GuestClaimEntry? {
        get { self[GuestClaimEntryKey.self] }
        set { self[GuestClaimEntryKey.self] = newValue }
    }
}

/// The profile row that opens the claim.
struct GuestClaimRow: View {
    let spanish: Bool
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            HStack(spacing: 16) {
                Image(systemName: "tray.and.arrow.down").frame(width: 24).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(GuestClaimCopy(spanish: spanish).title).font(.body)
                    Text(spanish ? "Tienes datos de invitado en este iPhone." : "You have guest data on this iPhone.")
                        .font(.footnote).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.footnote).foregroundStyle(.secondary).accessibilityHidden(true)
            }.padding(.vertical, 12).frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("guest.claim.row")
    }
}

struct GuestClaimSheet: View {
    @ObservedObject var model: GuestClaimModel
    let close: () -> Void

    private var copy: GuestClaimCopy { GuestClaimCopy(spanish: model.spanish) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    content
                }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(WelcomePalette.background)
            .navigationTitle("").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: model.phase == .discarded || model.phase == .finished ? copy.done : copy.later,
                                     disabled: isRunning, identifier: "guest.claim.close", action: close)
            }
        }
        .tint(WelcomePalette.pine)
        .interactiveDismissDisabled(isRunning)
        .task { await model.load() }
        .alert(copy.discardTitle, isPresented: $model.confirmingDiscard) {
            Button(model.spanish ? "Cancelar" : "Cancel", role: .cancel) {}
            Button(copy.discard, role: .destructive) { Task { await model.discard() } }
                .accessibilityIdentifier("guest.claim.discard.confirm")
        } message: { Text(copy.discardMessage) }
        .accessibilityIdentifier("guest.claim")
    }

    private var isRunning: Bool {
        if case .running = model.phase { return true }
        return model.discarding
    }

    @ViewBuilder private var content: some View {
        switch model.phase {
        case .loading:
            RegistrationHeading(title: copy.title, detail: "")
            ProgressView().accessibilityIdentifier("guest.claim.loading")
        case .nothingToMove:
            heading(copy.nothingToMove, id: "guest.claim.nothing")
            discardButton
        case .unreadable:
            heading(copy.unreadable, id: "guest.claim.unreadable")
        case .preview:
            heading(copy.previewIntro, id: "guest.claim.intro")
            preview
            RegistrationButton(title: copy.move, action: { Task { await model.start() } })
                .accessibilityIdentifier("guest.claim.start")
            discardButton
        case .running(let done, let total):
            heading(copy.keepsCopy, id: "guest.claim.keeps")
            ProgressView(value: Double(done), total: Double(max(total, 1)))
            Text(copy.running(done, total)).font(.body).accessibilityIdentifier("guest.claim.progress")
        case .finished:
            heading(copy.finished(model.moved), id: "guest.claim.finished")
            if model.moved.refused > 0 { Text(copy.refused(model.moved.refused)).font(.body).accessibilityIdentifier("guest.claim.refused") }
            Text(copy.staying(plans: model.moved.stayingPlans)).font(.body).foregroundStyle(.secondary)
            Text(copy.finishedKeeps).font(.body).foregroundStyle(.secondary)
            discardButton
        case .stopped(let reason):
            heading(copy.stopped(reason), id: "guest.claim.stopped")
            if reason != .signedOut {
                RegistrationButton(title: copy.retry, action: { Task { await model.retry() } })
                    .accessibilityIdentifier("guest.claim.retry")
            }
        case .discarded:
            heading(copy.discarded, id: "guest.claim.discarded")
        }
    }

    /// The title, then one sentence the tests and VoiceOver can find by its own id.
    private func heading(_ detail: String, id: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            RegistrationHeading(title: copy.title, detail: "")
            if !detail.isEmpty { Text(detail).font(.body).foregroundStyle(.secondary).accessibilityIdentifier(id) }
        }
    }

    private var preview: some View {
        VStack(alignment: .leading, spacing: 14) {
            if model.remaining.accounts > 0 { line(copy.accounts(model.remaining.accounts), "guest.claim.accounts") }
            if model.remaining.movements > 0 { line(copy.movements(model.remaining.movements), "guest.claim.movements") }
            if model.remaining.renamed > 0 {
                Text(copy.renamed(model.remaining.renamed)).font(.footnote).foregroundStyle(.secondary)
                    .accessibilityIdentifier("guest.claim.renamed")
            }
            Divider()
            Text(copy.staying(plans: model.remaining.stayingPlans)).font(.body).foregroundStyle(.secondary)
                .accessibilityIdentifier("guest.claim.staying")
            Text(copy.keepsCopy).font(.footnote).foregroundStyle(.secondary)
        }
    }

    private func line(_ text: String, _ identifier: String) -> some View {
        Text(text).font(.system(.title3, weight: .semibold)).accessibilityIdentifier(identifier)
    }

    private var discardButton: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button(role: .destructive) { model.askToDiscard() } label: {
                Text(copy.discard).frame(maxWidth: .infinity, minHeight: 44)
            }
            .disabled(model.discarding)
            .accessibilityIdentifier("guest.claim.discard")
            if model.discardFailed { Text(copy.discardFailed).font(.footnote).foregroundStyle(.secondary) }
        }
    }
}
