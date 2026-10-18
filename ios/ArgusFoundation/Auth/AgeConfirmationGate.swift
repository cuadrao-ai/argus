import SwiftUI

@MainActor
struct AgeConfirmationGate<Content: View>: View {
    @StateObject private var model: AgeConfirmationModel
    @State private var checked = false
    @ViewBuilder let content: () -> Content

    init(model: AgeConfirmationModel? = nil, @ViewBuilder content: @escaping () -> Content) {
        #if DEBUG
        let fixture = AgeConfirmationHarness.legalEntryModel()
        #else
        let fixture: AgeConfirmationModel? = nil
        #endif
        _model = StateObject(wrappedValue: model ?? fixture ?? AgeConfirmationModel(checker: AppleAgeRangeChecker()))
        self.content = content
    }

    private var actionTitle: String {
        switch model.state {
        case .sharingRequired: String(localized: "age.confirmation.share")
        case .unavailable: String(localized: "age.confirmation.retry")
        default: "Continuar"
        }
    }

    var body: some View {
        Group {
            if model.state == .allowed {
                content()
            } else {
                VStack(alignment: .leading, spacing: 24) {
                    if model.confirmation == nil && model.state != .under18 {
                        Toggle("age.confirmation.checkbox", isOn: $checked)
                            .toggleStyle(AgeCheckboxStyle())
                            .accessibilityIdentifier("age.confirmation.checkbox")
                    }
                    if model.state == .under18 {
                        Text("age.confirmation.under18").accessibilityIdentifier("age.confirmation.refused")
                        if let terms = CuadraoLegalURLs.ageGateTerms() {
                            Link("age.confirmation.terms", destination: terms)
                                .frame(minHeight: 44)
                                .accessibilityIdentifier("age.confirmation.terms")
                        }
                    } else {
                        if model.state == .sharingRequired {
                            Text("age.confirmation.sharingRequired").accessibilityIdentifier("age.confirmation.error")
                        } else if model.state == .unavailable {
                            Text("age.confirmation.unavailable").accessibilityIdentifier("age.confirmation.error")
                        }
                        RegistrationButton(title: actionTitle, busy: model.state == .checking,
                                           enabled: checked || model.confirmation != nil) {
                            Task { await model.authorize(checked: checked) }
                        }
                        .accessibilityIdentifier("age.confirmation.continue")
                    }
                    Spacer()
                }
                .padding(28)
                .background(WelcomePalette.background.ignoresSafeArea())
                .foregroundStyle(WelcomePalette.ink)
            }
        }
        .task {
            if model.confirmation != nil, model.state == .idle { await model.authorize(checked: false) }
        }
    }
}

private struct AgeCheckboxStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button { configuration.isOn.toggle() } label: {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: configuration.isOn ? "checkmark.square.fill" : "square")
                    .foregroundStyle(WelcomePalette.pine)
                configuration.label.multilineTextAlignment(.leading)
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(configuration.isOn ? .isSelected : [])
        .accessibilityValue(configuration.isOn ? Text("1") : Text("0"))
    }
}
