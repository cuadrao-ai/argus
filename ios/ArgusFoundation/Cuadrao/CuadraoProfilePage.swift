import SwiftUI

enum CuadraoProfilePageConnection {
    case preview
    case connected(appearance: Binding<AppearancePreference>, profile: ProfileAuthModel)
}

struct CuadraoProfilePage: View {
    let route: CanvasProfileRoute
    @Binding var settings: CuadraoProfileSettingsDraft
    let spanish: Bool
    let includeExamples: Bool
    let connection: CuadraoProfilePageConnection
    @State private var notice: String?
    @State private var deletingAccount = false

    init(route: CanvasProfileRoute, profile: Binding<CanvasProfileDraft>, spanish: Bool, includeExamples: Bool) {
        self.init(route: route, settings: profile.settings, spanish: spanish,
                  includeExamples: includeExamples, connection: .preview)
    }

    init(route: CanvasProfileRoute, settings: Binding<CuadraoProfileSettingsDraft>, spanish: Bool,
         includeExamples: Bool, connection: CuadraoProfilePageConnection) {
        self.route = route; _settings = settings; self.spanish = spanish
        self.includeExamples = includeExamples; self.connection = connection
    }

    var body: some View {
        Group {
            if route == .feedback {
                CuadraoFeedbackPage(saved: $settings.feedback, spanish: spanish)
            } else {
                Form {
                    content.listRowBackground(CanvasSettingsStyle.surface)
                }
            }
        }
            .environment(\.defaultMinListRowHeight, 52)
            .scrollContentBackground(.hidden).background(WelcomePalette.background)
            .navigationTitle(route.title(spanish)).navigationBarTitleDisplayMode(.large)
            .toolbar(.visible, for: .navigationBar)
            .navigationDestination(isPresented: $deletingAccount) {
                if let deletion = connectedDeletion { ConnectedAccountDeletion(model: deletion) }
            }
            .alert(notice ?? "", isPresented: Binding(get: { notice != nil }, set: { if !$0 { notice = nil } })) {
                Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.43385c465a", spanish: spanish), role: .cancel) { notice = nil }
            } message: {
                Text(CuadraoCopy.text("copy.cuadraoProfilePage.29f88f2cfc", spanish: spanish))
            }
    }

    @ViewBuilder private var content: some View {
        switch route {
        case .preferences: preferences
        case .personalization: personalization
        case .notifications: notifications
        case .security: security
        case .privacy: privacy
        case .usage:
            Section {
                ContentUnavailableView(CuadraoCopy.text("copy.cuadraoProfilePage.3171e82523", spanish: spanish), systemImage: "chart.bar",
                    description: Text(CuadraoCopy.text("copy.cuadraoProfilePage.4f238c7d9d", spanish: spanish)))
            }
        case .help: help
        case .feedback: EmptyView()
        case .memory, .files, .conversations: records
        case .shared:
            empty(CuadraoCopy.text("copy.cuadraoProfilePage.a3905cbc44", spanish: spanish), detail: CuadraoCopy.text("copy.cuadraoProfilePage.e1d7289cc8", spanish: spanish))
        case .removed:
            empty(CuadraoCopy.text("copy.cuadraoProfilePage.c5bc833234", spanish: spanish), detail: CuadraoCopy.text("copy.cuadraoProfilePage.b63961507f", spanish: spanish))
        case .voice:
            Section {
                CuadraoVoicePreference(spanish: spanish)
                LabeledContent(CuadraoCopy.text("copy.cuadraoProfilePage.98633ea3c0", spanish: spanish), value: CuadraoCopy.text("copy.cuadraoProfilePage.ab3aeb0112", spanish: spanish))
            } footer: {
                if CuadraoFirstRelease.shows(.personalization) {
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.e6c34c7e20", spanish: spanish))
                } else {
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.650560a010", spanish: spanish))
                }
            }
        case .advanced:
            Section {
                previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.3c7c7cef20", spanish: spanish))
                previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.8a579fc241", spanish: spanish))
            }
        case .personal, .invitations: EmptyView()
        }
    }

    private var preferences: some View {
        Group {
            Section {
                switch connection {
                case .preview: CuadraoAppearancePicker(spanish: spanish)
                case .connected(let appearance, _): CuadraoAppearanceChoices(spanish: spanish, selection: appearance)
                }
            } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.6d3e76f91f", spanish: spanish)) }
              footer: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.b894f61cc1", spanish: spanish)) }
            Section {
                LabeledContent(CuadraoCopy.text("copy.cuadraoProfilePage.98633ea3c0", spanish: spanish)) { Text(CuadraoCopy.text("copy.cuadraoProfilePage.244f0f8d3d", spanish: spanish)).foregroundStyle(.secondary) }
                    .accessibilityIdentifier("cuadrao.profile.language")
            }
            Section {
                switch connection {
                case .preview:
                    LabeledContent(CuadraoCopy.text("copy.connectedProfileCurrencyRow.8ceb934024", spanish: spanish)) {
                        CuadraoChoiceMenu(title: CuadraoCopy.text("copy.connectedProfileCurrencyRow.8ceb934024", spanish: spanish),
                            selection: $settings.currency, values: PlanCurrency.supported, valueTitle: { $0 })
                            .accessibilityIdentifier("cuadrao.profile.currency")
                    }
                case .connected(_, let profile):
                    ConnectedProfileCurrencyRow(model: profile, spanish: spanish)
                }
            } header: { Text(CuadraoCopy.text("copy.connectedTransactionSheet.9b96ad5816", spanish: spanish)) }
              footer: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.854936f059", spanish: spanish)) }
            if CuadraoFirstRelease.shows(.voice) || CuadraoFirstRelease.shows(.advanced) {
                Section { link(.voice); link(.advanced) }
            }
        }
    }

    private var personalization: some View {
        Group {
            Section {
                Picker(CuadraoCopy.text("copy.cuadraoProfilePage.26c969fea4", spanish: spanish), selection: $settings.responseLength) {
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.3749b3ae30", spanish: spanish)).tag(0)
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.91a73e61d9", spanish: spanish)).tag(1)
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.7ea2d26630", spanish: spanish)).tag(2)
                }
                Picker(CuadraoCopy.text("copy.cuadraoProfilePage.33744e618c", spanish: spanish), selection: $settings.tone) {
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.1af23c2bae", spanish: spanish)).tag(0)
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.3f8820339a", spanish: spanish)).tag(1)
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.60c71eac01", spanish: spanish)).tag(2)
                }
            } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.acb5baefff", spanish: spanish)) }
            Section {
                TextField(CuadraoCopy.text("copy.cuadraoProfilePage.ba489210bb", spanish: spanish), text: $settings.instructions, axis: .vertical)
                    .lineLimit(4...8)
            } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.d2392bf7bf", spanish: spanish)) }
              footer: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.254f985940", spanish: spanish)) }
            if CuadraoFirstRelease.shows(.memory) { Section { link(.memory) } }
        }
    }

    private var notifications: some View {
        Group {
            Section {
                // Release rule (fc7650ea/#787): the "Por correo / By email" toggle is removed.
                Toggle(CuadraoCopy.text("copy.cuadraoProfilePage.187489ae69", spanish: spanish), isOn: $settings.push)
            } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.a0cea7d2a6", spanish: spanish)) }
              footer: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.8e2c6cb930", spanish: spanish)) }
            Section {
                Toggle(CuadraoCopy.text("copy.cuadraoProfilePage.93f1c1ad0f", spanish: spanish), isOn: $settings.budgets)
                Toggle(CuadraoCopy.text("copy.cuadraoProfilePage.c3ffb867e0", spanish: spanish), isOn: $settings.goals)
                Toggle(CuadraoCopy.text("copy.cuadraoProfilePage.8c28ea141f", spanish: spanish), isOn: $settings.payments)
                Toggle(CuadraoCopy.text("copy.cuadraoProfilePage.783c0fd8f1", spanish: spanish), isOn: $settings.records)
                Toggle(CuadraoCopy.text("copy.cuadraoHouseholdSheet.b845d91db6", spanish: spanish), isOn: $settings.household)
            } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.b9584dcb70", spanish: spanish)) }
            Section {
                Toggle(CuadraoCopy.text("copy.cuadraoProfilePage.11e90aae9d", spanish: spanish), isOn: $settings.quietHours)
                if settings.quietHours {
                    DatePicker(CuadraoCopy.text("copy.cuadraoProfilePage.e0979ec757", spanish: spanish), selection: $settings.quietStart, displayedComponents: .hourAndMinute)
                        .accessibilityIdentifier("cuadrao.quiet.start")
                    DatePicker(CuadraoCopy.text("copy.cuadraoProfilePage.cd188379f8", spanish: spanish), selection: $settings.quietEnd, displayedComponents: .hourAndMinute)
                        .accessibilityIdentifier("cuadrao.quiet.end")
                }
            }
        }
    }

    private var security: some View {
        Group {
            Section { previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.cde3685914", spanish: spanish)) }
            Section {
                LabeledContent(CuadraoCopy.text("copy.cuadraoProfilePage.999d5ad00b", spanish: spanish), value: CuadraoCopy.text("copy.cuadraoProfilePage.230a57f1df", spanish: CuadraoCopy.isSpanish()))
                previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.cf7d7f6d77", spanish: spanish))
                previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.827752ebf1", spanish: spanish))
            } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.70971444f2", spanish: spanish)) }
              footer: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.d79aa7158e", spanish: spanish)) }
        }
    }

    private var privacy: some View {
        Group {
            if CuadraoFirstRelease.shows(.memory) || CuadraoFirstRelease.shows(.files) || CuadraoFirstRelease.shows(.conversations) {
                Section {
                    link(.memory); link(.files); link(.conversations)
                } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.ce43886b7d", spanish: spanish)) }
            }
            if CuadraoFirstRelease.savedReceipts, case .connected(_, let profile) = connection, let journey = profile.receiptJourney {
                ReceiptReadingSetting(model: journey, spanish: spanish)
            }
            if CuadraoFirstRelease.shows(.shared) || CuadraoFirstRelease.shows(.removed) {
                Section {
                    link(.shared); link(.removed)
                } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.76b002b9ac", spanish: spanish)) }
            }
            Section {
                Button(CuadraoCopy.text("copy.cuadraoProfilePage.a094025062", spanish: spanish), role: .destructive) {
                    if let deletion = connectedDeletion {
                        deletion.finish()
                        deletingAccount = true
                    } else {
                        notice = CuadraoCopy.text("copy.cuadraoProfilePage.a094025062", spanish: spanish)
                    }
                }
                .foregroundStyle(.red)
                .accessibilityIdentifier("cuadrao.profile.deleteAccount")
            } footer: {
                if CuadraoFirstRelease.shows(.memory) {
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.0ebaf506d1", spanish: spanish))
                } else {
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.332280c2f1", spanish: spanish))
                }
            }
        }
    }

    private var connectedDeletion: AccountDeletionModel? {
        if case .connected(_, let profile) = connection { profile.deletion } else { nil }
    }

    private var records: some View {
        let kind: CanvasSearchKind = route == .memory ? .memory : route == .files ? .files : .chats
        let rows = includeExamples ? CanvasSearchReference.examples(spanish).filter { $0.kind == kind } : []
        return Group {
            Section {
                ForEach(rows) { item in
                    NavigationLink {
                        CuadraoSearchReferenceDetail(item: item, spanish: spanish,
                            source: item.kind == .memory ? CanvasSearchReference.examples(spanish).first { $0.id == "chat-cd" } : nil)
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(item.title)
                            Text(item.detail).font(.caption).foregroundStyle(.secondary)
                        }.padding(.vertical, 6)
                    }
                }
                if rows.isEmpty { Text(CuadraoCopy.text("copy.cuadraoProfilePage.769c6d2a83", spanish: spanish)).foregroundStyle(.secondary) }
            } footer: {
                if route == .memory {
                    Text(CuadraoCopy.text("copy.cuadraoProfilePage.14a09af4aa", spanish: spanish))
                }
            }
            if route == .conversations && CuadraoFirstRelease.showsConversationBulkActions {
                Section {
                    previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.94e788c836", spanish: spanish))
                    previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.430d2f5049", spanish: spanish))
                    previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.d02b935981", spanish: spanish))
                }
            }
        }
    }

    private var help: some View {
        Group {
            Section {
                link(.feedback)
            }
            Section {
                switch connection {
                case .preview:
                    previewAction(CuadraoCopy.text("copy.connectedCuadraoProfile.2fe6836750", spanish: spanish))
                    previewAction(CuadraoCopy.text("copy.cuadraoProfilePage.3a2527a0ac", spanish: spanish))
                case .connected(_, let profile):
                    let legal = CuadraoLegalURLs.current
                    if legal.hasPages {
                        if let terms = legal.terms {
                            Link(CuadraoCopy.text("copy.connectedCuadraoProfile.2fe6836750", spanish: spanish), destination: terms)
                                .accessibilityIdentifier("release.legal.terms")
                        }
                        if let privacy = legal.privacy {
                            Link(CuadraoCopy.text("copy.cuadraoProfilePage.3a2527a0ac", spanish: spanish), destination: privacy)
                                .accessibilityIdentifier("release.legal.privacy")
                        }
                    } else {
                        Text(CuadraoCopy.text("copy.connectedCuadraoProfile.7cc578247d", spanish: spanish))
                    }
                }
            } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.e9a2ff8d1a", spanish: spanish)) }
        }
    }

    @ViewBuilder private func link(_ route: CanvasProfileRoute) -> some View {
        if CuadraoFirstRelease.shows(route) {
            NavigationLink(value: route) {
                HStack(spacing: 14) {
                    CanvasProfileIcon(route: route)
                    Text(route.title(spanish)).frame(minHeight: 30)
                }
            }
        }
    }
    private func previewAction(_ title: String) -> some View {
        Button(title) { notice = title }.foregroundStyle(.primary).frame(minHeight: 30)
    }
    private func empty(_ title: String, detail: String) -> some View {
        ContentUnavailableView(title, systemImage: route.symbol, description: Text(detail))
    }
}

/// AI reading of receipts, on or off for this account. The long explanation lives in the footer.
private struct ReceiptReadingSetting: View {
    @ObservedObject var model: ReceiptJourneyModel
    let spanish: Bool

    var body: some View {
        let copy = ReceiptJourneyCopy(spanish: spanish)
        Section {
            Toggle(copy.settingTitle, isOn: Binding(get: { model.readingAllowed }, set: { model.setReadingAllowed($0) }))
                .accessibilityIdentifier("cuadrao.privacy.receiptReading")
        } footer: { Text(copy.settingFooter) }
    }
}
