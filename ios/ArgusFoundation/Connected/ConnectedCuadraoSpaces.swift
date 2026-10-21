import SwiftUI

struct ConnectedCuadraoSpaces: View {
    @ObservedObject var model: HouseholdModel
    @Binding var destination: AppDestination
    @EnvironmentObject private var auth: ProfileAuthModel
    @Environment(\.locale) private var locale
    @State private var showsSpaces = false
    /// A sheet opens another only after it has gone, so the host keeps the action until then.
    @State private var afterSpaces: (() -> Void)?
    private var policy: ConnectedSpacesPolicy { ConnectedSpacesPolicy(model: model) }
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if model.isAvailable {
                CuadraoSpaceSelectorLayout(selection: model.active ? "household" : "personal",
                    addTitle: NSLocalizedString("household.addOrManage", comment: ""), addIdentifier: "household.add",
                    showsAdd: CuadraoFirstRelease.showsExtraSpaces,
                    add: { showsSpaces = true }) {
                    Button { Task { await model.select(nil) } } label: {
                        CuadraoSpaceLabel(title: NSLocalizedString("household.personal", comment: ""), selected: !model.active)
                            .contentShape(Rectangle())
                    }.buttonStyle(.plain).id("personal").accessibilityIdentifier("household.personal")
                        .accessibilityAddTraits(model.active ? [] : [.isSelected])
                    if policy.showsHouseholdMenu {
                        Menu {
                            ForEach(model.households) { item in
                                Button(item.name ?? NSLocalizedString("household.title", comment: "")) {
                                    Task { await model.select(item.id) }
                                }.accessibilityIdentifier("household.select." + item.id.uuidString)
                            }
                            Button("household.manage") { model.showManagement = true }
                        } label: {
                            CuadraoSpaceLabel(title: model.household?.name ?? NSLocalizedString("household.title", comment: ""), selected: model.active)
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain).id("household").accessibilityIdentifier("household.selector")
                            .accessibilityAddTraits(model.active ? [.isSelected] : [])
                    } else {
                        Button { Task { await model.startHousehold() } } label: {
                            CuadraoSpaceAddLabel(title: NSLocalizedString("household.title", comment: ""))
                        }.buttonStyle(.plain).id("household").accessibilityIdentifier("household.start")
                            .accessibilityLabel(NSLocalizedString("household.addHousehold", comment: ""))
                    }
                }
                if model.errorKey == "household.accessEnded" {
                    Text("household.accessEnded").font(.caption).accessibilityIdentifier("household.accessEnded")
                }
                if model.pending != nil {
                    HStack {
                        Text("household.uncertain")
                        Button("accounts.retry") { Task { await model.retry() } }
                            .accessibilityIdentifier("household.pending.retry").frame(minHeight: 44)
                    }.font(.caption)
                }
            } else if model.availability == .unavailable {
                HStack {
                    Text("household.loadError")
                    Button("accounts.retry") { Task { await model.refresh() } }
                        .accessibilityIdentifier("household.availability.retry").frame(minHeight: 44)
                }.font(.caption)
            } else {
                Text("household.personal").font(.subheadline.weight(.semibold)).frame(minHeight: 44)
            }
        }
        .sheet(isPresented: $showsSpaces, onDismiss: { let run = afterSpaces; afterSpaces = nil; run?() }) {
            CuadraoSpacesSheet(source: ConnectedSpacesSource(policy: policy,
                showsExtraSpaces: CuadraoFirstRelease.showsExtraSpaces, spanish: spanish,
                startHousehold: { afterSpaces = { Task { await model.startHousehold() } } },
                manageHousehold: { afterSpaces = { model.showManagement = true } }), spanish: spanish)
        }
        .onAppear {
            model.navigateToAccounts = { destination = .accounts }
            model.addAccount = { Task { await model.select(nil); destination = .accounts; auth.accounts?.create() } }
        }
    }
}

/// Hogar leads into the real create and join flow; Negocio and Personalizado wait for a backend.
struct ConnectedSpacesSource: CuadraoSpacesSource {
    let policy: ConnectedSpacesPolicy
    let showsExtraSpaces: Bool
    let spanish: Bool
    let startHousehold: () -> Void
    let manageHousehold: () -> Void

    func choice(_ kind: CanvasSpaceKind, finish: @escaping () -> Void) -> CuadraoSpaceChoice {
        resolve(kind == .household ? policy.household : policy.extraSpace)
    }
    func manage(finish: @escaping () -> Void) -> CuadraoSpaceChoice { resolve(policy.manage) }

    private func resolve(_ outcome: ConnectedSpacesPolicy.Outcome) -> CuadraoSpaceChoice {
        switch outcome {
        case .startHousehold: .act(startHousehold)
        case .manageHousehold: .act(manageHousehold)
        case .comingSoon: .soon
        case .emptyManage: .page(AnyView(ConnectedSpacesEmpty()))
        }
    }
}

private struct ConnectedSpacesEmpty: View {
    var body: some View {
        VStack(spacing: 12) {
            Text("household.spaces.none").font(.subheadline).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading).accessibilityIdentifier("spaces.empty")
            Spacer(minLength: 0)
        }.padding(24).background(WelcomePalette.background)
            .navigationTitle(NSLocalizedString("household.manage", comment: "")).navigationBarTitleDisplayMode(.inline)
    }
}
