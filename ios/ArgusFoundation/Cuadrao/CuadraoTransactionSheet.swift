import SwiftUI

struct CuadraoTransactionAccount {
    let title: String
    let artwork: CanvasAccountKind?
    /// Drawn only when the connected account type has no Preview artwork.
    var symbol = "banknote"
}

/// The record-movement sheet: account header, one entry or review body, Back or Cancel, one primary action.
/// Every optional defaults to the Preview's own words and behavior.
struct CuadraoTransactionSheet<Content: View>: View {
    let account: CuadraoTransactionAccount
    let spanish: Bool
    let reviewing: Bool
    var title: String? = nil
    var primaryTitle: String? = nil
    var primaryEnabled = true
    var primaryBusy = false
    var primaryIdentifier: String? = nil
    var cancelDisabled = false
    var dismissDisabled = false
    var scrollTarget: String? = nil
    /// False when the body already names the account, so the name shows once.
    var showsAccountHeader = true
    let back: () -> Void
    let primary: () -> Void
    @ViewBuilder let content: () -> Content
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 28) {
                        if showsAccountHeader { HStack(spacing: 12) {
                            if let kind = account.artwork {
                                CanvasAccountIcon(kind: kind)
                            } else {
                                Image(systemName: account.symbol).font(.title3).foregroundStyle(WelcomePalette.pine)
                                    .frame(width: 23, height: 23).accessibilityHidden(true)
                            }
                            Text(account.title).font(CuadraoTypography.action)
                        }.padding(.top, 8) }
                        content()
                    }.padding(24)
                }
                .onChange(of: scrollTarget, initial: true) { _, target in
                    guard let target else { return }
                    withAnimation { proxy.scrollTo(target, anchor: .center) }
                }
            }.background(WelcomePalette.background)
                .navigationTitle(title ?? (reviewing ? (CuadraoCopy.text("copy.cuadraoTransactionSheet.427fc9b135", spanish: spanish)) : (CuadraoCopy.text("copy.canvasAccountPresentation.ef0cf39904", spanish: spanish))))
                .navigationBarTitleDisplayMode(.inline)
                .scrollDismissesKeyboard(.interactively)
                .toolbar {
                    CuadraoCancelToolbar(title: reviewing ? (CuadraoCopy.text("copy.cuadraoTransactionSheet.09b2a422c9", spanish: spanish)) : (CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish)), disabled: cancelDisabled) {
                        if reviewing { back() } else { dismiss() }
                    }
                }
                .safeAreaInset(edge: .bottom) {
                    RegistrationButton(title: primaryTitle ?? (reviewing ? (CuadraoCopy.text("copy.cuadraoAccountManagement.553ab1bf1a", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoTransactionSheet.a9a8d8a534", spanish: spanish))),
                                       busy: primaryBusy, enabled: primaryEnabled, action: primary)
                        .accessibilityIdentifier(primaryIdentifier ?? "")
                        .padding(24).background(WelcomePalette.background)
                }
                .interactiveDismissDisabled(dismissDisabled)
        }.tint(WelcomePalette.pine)
    }
}
