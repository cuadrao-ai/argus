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
                Button(spanish ? "Entendido" : "Got it", role: .cancel) { notice = nil }
            } message: {
                Text(spanish ? "Esta acción aún no está conectada en la vista previa. No se cambia ni se envía información de tu cuenta."
                     : "This action is not connected in the preview. No account information is changed or sent.")
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
                ContentUnavailableView(spanish ? "Tu uso, aquí" : "Your usage, here", systemImage: "chart.bar",
                    description: Text(spanish ? "Verás tu disponibilidad y cuándo se renueva al conectar tu cuenta." : "Your allowance and reset time will appear when your account is connected."))
            }
        case .help: help
        case .feedback: EmptyView()
        case .memory, .files, .conversations: records
        case .shared:
            empty(spanish ? "Sin conversaciones compartidas" : "No shared conversations", detail: spanish ? "Los enlaces que compartas aparecerán aquí." : "Links you share will appear here.")
        case .removed:
            empty(spanish ? "Sin movimientos eliminados" : "No removed activity", detail: spanish ? "Aquí podrás revisar los movimientos disponibles para restaurar." : "Review activity available to restore here.")
        case .voice:
            Section {
                CuadraoVoicePreference(spanish: spanish)
                LabeledContent(spanish ? "Idioma" : "Language", value: spanish ? "El de la conversación" : "Matches the conversation")
            } footer: {
                if CuadraoFirstRelease.shows(.personalization) {
                    Text(spanish ? "La voz cambia cómo suena Cuadrao. El tono y la extensión se eligen en Personalización. Esta vista previa no activa el micrófono."
                         : "Voice changes how Cuadrao sounds. Choose response tone and length in Personalization. This preview does not activate the microphone.")
                } else {
                    Text(spanish ? "La voz cambia cómo suena Cuadrao. Esta vista previa no activa el micrófono."
                         : "Voice changes how Cuadrao sounds. This preview does not activate the microphone.")
                }
            }
        case .advanced:
            Section {
                previewAction(spanish ? "Sugerencias" : "Suggestions")
                previewAction(spanish ? "Agitar para reportar un problema" : "Shake to report a problem")
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
            } header: { Text(spanish ? "Apariencia" : "Appearance") }
              footer: { Text(spanish ? "Sistema sigue la apariencia de tu iPhone." : "System follows your iPhone's appearance.") }
            Section {
                LabeledContent(spanish ? "Idioma" : "Language") { Text(spanish ? "Español" : "English").foregroundStyle(.secondary) }
                    .accessibilityIdentifier("cuadrao.profile.language")
            }
            Section {
                switch connection {
                case .preview:
                    LabeledContent(spanish ? "Moneda preferida" : "Preferred currency") {
                        CuadraoChoiceMenu(title: spanish ? "Moneda preferida" : "Preferred currency",
                            selection: $settings.currency, values: PlanCurrency.supported, valueTitle: { $0 })
                            .accessibilityIdentifier("cuadrao.profile.currency")
                    }
                case .connected(_, let profile):
                    ConnectedProfileCurrencyRow(model: profile, spanish: spanish)
                }
            } header: { Text(spanish ? "Moneda" : "Currency") }
              footer: { Text(spanish ? "Elegir una moneda no convierte ni combina tus balances." : "Choosing a currency does not convert or combine your balances.") }
            if CuadraoFirstRelease.shows(.voice) || CuadraoFirstRelease.shows(.advanced) {
                Section { link(.voice); link(.advanced) }
            }
        }
    }

    private var personalization: some View {
        Group {
            Section {
                Picker(spanish ? "Extensión" : "Length", selection: $settings.responseLength) {
                    Text(spanish ? "Automática" : "Automatic").tag(0)
                    Text(spanish ? "Breve" : "Brief").tag(1)
                    Text(spanish ? "Detallada" : "Detailed").tag(2)
                }
                Picker(spanish ? "Tono" : "Tone", selection: $settings.tone) {
                    Text(spanish ? "Natural" : "Natural").tag(0)
                    Text(spanish ? "Directo" : "Direct").tag(1)
                    Text(spanish ? "Didáctico" : "Educational").tag(2)
                }
            } header: { Text(spanish ? "Respuestas" : "Responses") }
            Section {
                TextField(spanish ? "Qué debería tener en cuenta" : "What should it keep in mind", text: $settings.instructions, axis: .vertical)
                    .lineLimit(4...8)
            } header: { Text(spanish ? "Tus instrucciones" : "Your instructions") }
              footer: { Text(spanish ? "Son preferencias que tú eliges. No son recuerdos inferidos de tus chats. En esta vista previa no se envían al asistente." : "These are preferences you choose, not memories inferred from chats. This preview does not send them to the assistant.") }
            if CuadraoFirstRelease.shows(.memory) { Section { link(.memory) } }
        }
    }

    private var notifications: some View {
        Group {
            Section {
                // Release rule (fc7650ea/#787): the "Por correo / By email" toggle is removed.
                Toggle(spanish ? "En este dispositivo" : "On this device", isOn: $settings.push)
            } header: { Text(spanish ? "Dónde recibirlas" : "Delivery") }
              footer: { Text(spanish ? "Novedades sigue disponible aunque desactives estos avisos. Los controles de esta vista previa no solicitan permisos ni envían notificaciones." : "Updates remain available when these alerts are off. Preview controls do not request permission or send notifications.") }
            Section {
                Toggle(spanish ? "Presupuestos" : "Budgets", isOn: $settings.budgets)
                Toggle(spanish ? "Metas" : "Goals", isOn: $settings.goals)
                Toggle(spanish ? "Pagos próximos" : "Upcoming payments", isOn: $settings.payments)
                Toggle(spanish ? "Por revisar" : "Needs review", isOn: $settings.records)
                Toggle(spanish ? "Hogar" : "Household", isOn: $settings.household)
            } header: { Text(spanish ? "Sobre qué" : "Topics") }
            Section {
                Toggle(spanish ? "Horario de descanso" : "Quiet hours", isOn: $settings.quietHours)
                if settings.quietHours {
                    DatePicker(spanish ? "Desde" : "From", selection: $settings.quietStart, displayedComponents: .hourAndMinute)
                        .accessibilityIdentifier("cuadrao.quiet.start")
                    DatePicker(spanish ? "Hasta" : "Until", selection: $settings.quietEnd, displayedComponents: .hourAndMinute)
                        .accessibilityIdentifier("cuadrao.quiet.end")
                }
            }
        }
    }

    private var security: some View {
        Group {
            Section { previewAction(spanish ? "Cambiar contraseña" : "Change password") }
            Section {
                LabeledContent(spanish ? "Este dispositivo" : "This device", value: "iPhone")
                previewAction(spanish ? "Cerrar otras sesiones" : "Sign out other sessions")
                previewAction(spanish ? "Cerrar todas las sesiones" : "Sign out all sessions")
            } header: { Text(spanish ? "Sesiones" : "Sessions") }
              footer: { Text(spanish ? "Las sesiones reales se mostrarán al conectar tu cuenta." : "Real sessions will appear when your account is connected.") }
        }
    }

    private var privacy: some View {
        Group {
            if CuadraoFirstRelease.shows(.memory) || CuadraoFirstRelease.shows(.files) || CuadraoFirstRelease.shows(.conversations) {
                Section {
                    link(.memory); link(.files); link(.conversations)
                } header: { Text(spanish ? "Tus datos" : "Your data") }
            }
            if CuadraoFirstRelease.savedReceipts, case .connected(_, let profile) = connection, let journey = profile.receiptJourney {
                ReceiptReadingSetting(model: journey, spanish: spanish)
            }
            if CuadraoFirstRelease.shows(.shared) || CuadraoFirstRelease.shows(.removed) {
                Section {
                    link(.shared); link(.removed)
                } header: { Text(spanish ? "Compartir y recuperar" : "Sharing and recovery") }
            }
            Section {
                Button(spanish ? "Eliminar cuenta" : "Delete account", role: .destructive) {
                    if let deletion = connectedDeletion {
                        deletion.finish()
                        deletingAccount = true
                    } else {
                        notice = spanish ? "Eliminar cuenta" : "Delete account"
                    }
                }
                .foregroundStyle(.red)
                .accessibilityIdentifier("cuadrao.profile.deleteAccount")
            } footer: {
                if CuadraoFirstRelease.shows(.memory) {
                    Text(spanish ? "Compartir un hogar no comparte tus chats, archivos ni memoria." : "Joining a household does not share your chats, files or memory.")
                } else {
                    Text(spanish ? "Compartir un hogar no comparte tus chats ni archivos." : "Joining a household does not share your chats or files.")
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
                if rows.isEmpty { Text(spanish ? "Nada guardado todavía." : "Nothing saved yet.").foregroundStyle(.secondary) }
            } footer: {
                if route == .memory {
                    Text(spanish ? "Memoria guarda contexto que confirmas. Tus balances y movimientos permanecen en sus propios registros." : "Memory holds context you confirm. Balances and activity stay in their own records.")
                }
            }
            if route == .conversations && CuadraoFirstRelease.showsConversationBulkActions {
                Section {
                    previewAction(spanish ? "Chats archivados" : "Archived chats")
                    previewAction(spanish ? "Eliminados recientemente" : "Recently deleted")
                    previewAction(spanish ? "Eliminar todas las conversaciones" : "Delete all conversations")
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
                    previewAction(spanish ? "Términos de uso" : "Terms of use")
                    previewAction(spanish ? "Política de privacidad" : "Privacy policy")
                case .connected(_, let profile):
                    let legal = CuadraoLegalURLs.current
                    if legal.hasPages {
                        if let terms = legal.terms {
                            Link(spanish ? "Términos de uso" : "Terms of use", destination: terms)
                                .accessibilityIdentifier("release.legal.terms")
                        }
                        if let privacy = legal.privacy {
                            Link(spanish ? "Política de privacidad" : "Privacy policy", destination: privacy)
                                .accessibilityIdentifier("release.legal.privacy")
                        }
                    } else {
                        Text(spanish ? "Los enlaces no están disponibles en este momento." : "These links aren't available right now.")
                    }
                }
            } header: { Text(spanish ? "Acerca de Cuadrao" : "About Cuadrao") }
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
