import SwiftUI
import CuadraoBook

/// What the on-device book shows: the shell when the book can be used, or an honest notice when it cannot.
struct GuestRoot: View {
    @ObservedObject var model: GuestBookModel
    @Binding var appearance: AppearancePreference
    let webURL: URL?
    let leave: () -> Void
    let deleteData: () async -> Bool
    @Environment(\.locale) private var locale
    @State private var confirmingDelete = false
    @State private var deleteFailed = false

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        switch model.phase {
        case .loading:
            WelcomePalette.brandPaper.ignoresSafeArea()
        case .ready:
            // The banner is its own row above the shell, so nothing the shell draws can sit under it.
            VStack(spacing: 0) {
                GuestModeBanner(spanish: spanish)
                GuestShell(model: model, appearance: $appearance, webURL: webURL, leave: leave, deleteData: deleteData)
            }
            .preferredColorScheme(appearance.colorScheme)
        case .newerVersion:
            notice(title: spanish ? "Actualiza Cuadrao para abrir este libro." : "Update Cuadrao to open this book.",
                   detail: spanish ? "Este libro se guardó con una versión más nueva de la app. No se cambió nada. Actualiza Cuadrao e inténtalo de nuevo."
                       : "This book was saved by a newer version of the app. Nothing was changed. Update Cuadrao and try again.",
                   identifier: "guest.notice.newer", offersDelete: false)
        case .unreadable:
            notice(title: spanish ? "No se pudo abrir tu libro." : "Your book could not be opened.",
                   detail: spanish ? "El archivo de este iPhone no se pudo leer. Puedes eliminarlo y empezar de nuevo."
                       : "The file on this iPhone could not be read. You can delete it and start again.",
                   identifier: "guest.notice.unreadable", offersDelete: true)
        }
    }

    private func notice(title: String, detail: String, identifier: String, offersDelete: Bool) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            Spacer(minLength: 0)
            RegistrationHeading(title: title, detail: detail)
            RegistrationButton(title: spanish ? "Volver" : "Back", action: leave)
                .accessibilityIdentifier("guest.notice.back")
            if offersDelete {
                Button(role: .destructive) { confirmingDelete = true } label: {
                    Text(spanish ? "Eliminar los datos de este iPhone" : "Delete this iPhone's data")
                        .frame(maxWidth: .infinity, minHeight: 44)
                }.accessibilityIdentifier("guest.notice.delete")
            }
            Spacer(minLength: 0)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .background(WelcomePalette.brandPaper.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink)
        .accessibilityIdentifier(identifier)
        .alert(GuestDeleteCopy.title(spanish), isPresented: $confirmingDelete) {
            Button(spanish ? "Cancelar" : "Cancel", role: .cancel) {}
            Button(GuestDeleteCopy.confirm(spanish), role: .destructive) {
                Task { if await !deleteData() { deleteFailed = true } }
            }.accessibilityIdentifier("guest.delete.confirm")
        } message: { Text(GuestDeleteCopy.message(spanish)) }
        .alert(GuestDeleteCopy.failed(spanish), isPresented: $deleteFailed) {
            Button(spanish ? "Entendido" : "Got it", role: .cancel) {}
        }
    }
}

enum GuestDeleteCopy {
    static func title(_ es: Bool) -> String { es ? "¿Eliminar los datos de este iPhone?" : "Delete this iPhone's data?" }
    static func confirm(_ es: Bool) -> String { es ? "Eliminar" : "Delete" }
    /// Pending approval: receipts were added to the list when the book gained them.
    static func message(_ es: Bool) -> String {
        es ? "Se borrarán tus cuentas, movimientos, presupuestos, metas y recibos de este iPhone. No se puede deshacer."
            : "Your accounts, activity, budgets, goals and receipts on this iPhone will be removed. This can't be undone."
    }
    static func failed(_ es: Bool) -> String { es ? "No se pudieron eliminar los datos. Inténtalo de nuevo." : "The data could not be deleted. Try again." }
}

/// The shared Cuadrao shell filled with the book: the same navigation bar, + tray, scroll folding and tabs,
/// with the assistant slot given to the add action because the book has no assistant.
struct GuestShell: View {
    @ObservedObject var model: GuestBookModel
    @Binding var appearance: AppearancePreference
    let webURL: URL?
    let leave: () -> Void
    let deleteData: () async -> Bool
    @Environment(\.locale) private var locale
    @State private var tab: CuadraoTab = .home
    @State private var navigationScroll = CuadraoNavigationScroll()
    @State private var planScroll = CuadraoNavigationScroll()
    @State private var searchScroll = CuadraoNavigationScroll()
    @State private var profileScroll = CuadraoNavigationScroll()
    @State private var profilePath: [GuestProfileRoute] = []
    @State private var homePath: [GuestRoute] = []
    @State private var planPath: [UUID] = []
    @State private var sheet: GuestSheet?
    @State private var capturing: ReceiptSourceChoice?
    @State private var captured: [(data: Data, name: String, pdf: Bool)]?
    @State private var receiptFailed = false
    @Environment(\.guestReceipts) private var receipts
    @State private var chat = CuadraoChatPreview(spanish: Locale.current.language.languageCode?.identifier == "es", includeExamples: false)

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        CuadraoAppShell(selection: $tab, chat: chat, spanish: spanish, showsNavigation: showsNavigation,
                        compact: scroll(for: tab)?.compact ?? false, avatar: .none, profileName: "",
                        addItems: addItems, hasAssistant: GuestAccessPolicy.hasAssistant) { _ in
            ForEach(CuadraoTab.allCases.filter { $0 != .assistant }) { item in
                content(item)
                    .toolbar(.hidden, for: .tabBar)
                    .tag(item)
            }
        }
        .environment(\.cuadraoCurrencyRules, GuestCurrencyRules.rules)
        .environment(\.guestAddReceipt) { capture($0) }
        .sheet(item: $sheet) { sheetContent($0) }
        .fullScreenCover(item: $capturing, onDismiss: {
            if let files = captured { captured = nil; keep(files) }
        }) { source in
            ReceiptNativePicker(source: source, spanish: spanish) { result in
                capturing = nil
                if case .success(let files) = result { captured = SavedReceiptFiles.prepared(files, source: source, spanish: spanish) }
            }.ignoresSafeArea()
        }
        .alert(GuestReceiptCopy(spanish: spanish).couldNotSave, isPresented: $receiptFailed) {
            Button(spanish ? "Entendido" : "Got it", role: .cancel) {}
        }
        .tint(WelcomePalette.pine)
        .foregroundStyle(WelcomePalette.ink)
        .background(WelcomePalette.background.ignoresSafeArea())
    }

    private var showsNavigation: Bool {
        switch tab {
        case .home: homePath.isEmpty
        case .profile: profilePath.isEmpty
        case .plan: planPath.isEmpty
        default: true
        }
    }

    private var addItems: [CuadraoAddItem] {
        GuestAccessPolicy.addActions(activeAccounts: model.book.activeAccounts.count).map { action in
            CuadraoAddItem(action: action) {
                switch action {
                case .account: sheet = .account(.create)
                case .transaction: sheet = .movement(.create(account: nil))
                case .plan: sheet = .plan(.create)
                case .scanCamera: capture(.scan)
                case .choosePhoto: capture(.photos)
                case .chooseFile: capture(.file)
                default: break
                }
            }
        }
    }

    private func capture(_ source: ReceiptSourceChoice) {
        #if DEBUG
        if CuadraoFirstRelease.savedReceiptsSample {
            keep(SampleSavedReceiptsTransport.files(for: source))
            return
        }
        #endif
        capturing = source == .scan && !SavedReceiptFiles.scannerAvailable ? .photos : source
    }

    /// Keeps the files on this iPhone and offers the first to a movement.
    private func keep(_ files: [(data: Data, name: String, pdf: Bool)]) {
        guard let receipts, let saved = try? receipts.save(files), let first = saved.first else { receiptFailed = true; return }
        sheet = .receiptSaved(first.id)
    }

    @ViewBuilder private func sheetContent(_ sheet: GuestSheet) -> some View {
        switch sheet {
        case .account(let mode):
            GuestAccountSheet(model: model, mode: mode, spanish: spanish).preferredColorScheme(appearance.colorScheme)
        case .movement(let mode):
            GuestMovementSheet(model: model, mode: mode, spanish: spanish).preferredColorScheme(appearance.colorScheme)
        case .archive(let id):
            CuadraoArchiveAccountReview(spanish: spanish) { _ = try? model.apply { try $0.settingArchived(id, true) } }
                .preferredColorScheme(appearance.colorScheme)
        case .archived:
            GuestArchivedAccounts(model: model, spanish: spanish).preferredColorScheme(appearance.colorScheme)
        case .plan(let mode):
            GuestPlanSheet(model: model, mode: mode, spanish: spanish).preferredColorScheme(appearance.colorScheme)
        case .contribution(let id):
            GuestContributionSheet(model: model, planID: id, spanish: spanish).preferredColorScheme(appearance.colorScheme)
        case .receiptSaved(let id):
            if let receipts {
                GuestReceiptSavedSheet(store: receipts, model: model, receiptID: id, spanish: spanish).preferredColorScheme(appearance.colorScheme)
            }
        case .attachReceipt(let movementID):
            if let receipts {
                GuestAttachReceiptSheet(store: receipts, model: model, movementID: movementID, spanish: spanish)
                    .preferredColorScheme(appearance.colorScheme)
            }
        }
    }

    /// A search result opens in the tab that owns it.
    private func open(_ target: GuestSearchTarget) {
        switch target {
        case .account(let id): tab = .home; homePath = [.account(id)]
        case .movement(let id): tab = .home; homePath = [.movement(id)]
        case .plan(let id): tab = .plan; planPath = [id]
        }
    }

    private func scroll(for item: CuadraoTab) -> CuadraoNavigationScroll? {
        switch item {
        case .home: navigationScroll
        case .plan: planScroll
        case .search: searchScroll
        case .profile: profileScroll
        case .assistant: nil
        }
    }

    @ViewBuilder private func content(_ item: CuadraoTab) -> some View {
        switch item {
        case .home:
            GuestHome(model: model, scroll: navigationScroll, active: tab == .home, path: $homePath, sheet: $sheet)
        case .plan:
            GuestPlanTab(model: model, scroll: planScroll, active: tab == .plan, path: $planPath, sheet: $sheet)
        case .search:
            GuestSearchTab(model: model, scroll: searchScroll, active: tab == .search, open: open)
        case .profile:
            GuestProfile(model: model, appearance: $appearance, path: $profilePath, webURL: webURL, leave: leave, deleteData: deleteData)
                .modifier(CuadraoNavigationScrollObserver(scroll: profileScroll, enabled: tab == .profile && profilePath.isEmpty))
        case .assistant:
            EmptyView()
        }
    }
}

struct GuestPlaceholderTab: View {
    let scroll: CuadraoNavigationScroll
    let active: Bool
    let title: String
    let detail: String
    let identifier: String

    var body: some View {
        ScrollView {
            CuadraoChartState(title: title, detail: detail)
                .padding(.horizontal, 24).padding(.top, 28).padding(.bottom, 32)
        }
        .safeAreaPadding(.bottom, 80)
        .background(WelcomePalette.background)
        .accessibilityIdentifier(identifier)
        .modifier(CuadraoNavigationScrollObserver(scroll: scroll, enabled: active))
    }
}
