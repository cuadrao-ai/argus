import SwiftUI

/// Preview-only reference surface. It uses the components users interact with.
struct CuadraoDesignGallery: View {
    @State private var spanish = !ProcessInfo.processInfo.arguments.contains("--design-english")
    @AppStorage(CuadraoAppearancePicker.storageKey) private var appearance = AppearancePreference.light
    @State private var originalAppearance: AppearancePreference?
    private var dark: Binding<Bool> { Binding(get: { appearance == .dark }, set: { appearance = $0 ? .dark : .light }) }
    @State private var largeText = false
    @State private var previewReducedMotion = false
    @State private var raw = ""
    @State private var accountError = ""
    @State private var amount = 0.0
    @State private var planError = ""
    @State private var currency = "DOP"
    @State private var distribution = false
    @State private var period: CanvasHistoryRange = .month
    @State private var toast: CuadraoToastMessage?
    @State private var retries = 0
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    controls
                    VStack(alignment: .leading, spacing: 12) {
                        Text(CuadraoCopy.text("copy.cuadraoDesignGallery.28230cdfd7", spanish: spanish)).font(CuadraoTypography.screen)
                        Text(CuadraoCopy.text("copy.cuadraoDesignGallery.bc6d27b574", spanish: spanish))
                            .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.1741e34c99", spanish: spanish)) {
                        Text(CuadraoCopy.text("copy.cuadraoDesignGallery.21ba752c62", spanish: spanish)).font(CuadraoTypography.feature)
                        Text(CuadraoCopy.text("copy.cuadraoDesignGallery.daeb973c09", spanish: spanish)).font(CuadraoTypography.section)
                        Text(CuadraoCopy.text("copy.cuadraoDesignGallery.6bfac39406", spanish: spanish)).font(CuadraoTypography.body)
                        Text("DOP 24,580.50").font(CuadraoTypography.amount).foregroundStyle(WelcomePalette.ink)
                            .lineLimit(1).minimumScaleFactor(0.5)
                        Text("DOP 3,240.00").font(CuadraoTypography.secondaryAmount)
                        Text("DOP 650.00").font(CuadraoTypography.rowAmount)
                        Text(CuadraoCopy.text("copy.cuadraoDesignGallery.15728a437d", spanish: spanish))
                            .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.5eda618350", spanish: spanish)) {
                        ViewThatFits(in: .horizontal) {
                            HStack { rowLabel; Spacer(); rowAmount }
                            VStack(alignment: .leading, spacing: 8) { rowLabel; rowAmount }
                        }
                        PlanPrimaryButton(title: CuadraoCopy.text("copy.cuadraoDesignGallery.c27a4762b9", spanish: spanish)) { }
                            .disabled(true).accessibilityIdentifier("gallery-action")
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.b8b296c419", spanish: spanish)) {
                        HStack {
                            Text(CuadraoCopy.text("copy.connectedCuadraoHome.8cce5d02a3", spanish: spanish)).font(CuadraoTypography.section)
                            Spacer()
                            CuadraoSectionAddButton(title: CuadraoCopy.text("copy.connectedCuadraoHome.10d1d9ce3f", spanish: spanish)) { }
                        }
                        HStack {
                            CuadraoChoiceMenu(title: CuadraoCopy.text("copy.connectedTransactionSheet.9b96ad5816", spanish: spanish), selection: $currency,
                                values: PlanCurrency.supported, valueTitle: { $0 })
                            Spacer()
                            CuadraoChoiceLabel(title: currency, selectable: false, locked: true)
                        }
                        CuadraoChartViewChoice(distribution: $distribution, spanish: spanish)
                        CuadraoHistoryPeriodChoice(range: $period, spanish: spanish)
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.f99f2d25c7", spanish: spanish)) {
                        CuadraoAmountField(raw: $raw, currency: $currency, error: $accountError, spanish: spanish)
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.7cac0c204d", spanish: spanish)) {
                        PlanAmountInput(value: $amount, currency: $currency, error: $planError,
                                        title: CuadraoCopy.text("copy.cuadraoDesignGallery.bde934cd65", spanish: spanish), identifier: "gallery-plan-amount", spanish: spanish)
                        Text(CuadraoCopy.text("copy.cuadraoDesignGallery.13fa9125be", spanish: spanish))
                            .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.d2a271f293", spanish: spanish)) {
                        CuadraoChartState(title: CuadraoCopy.text("copy.cuadraoDesignGallery.4fec8a8355", spanish: spanish),
                            detail: CuadraoCopy.text("copy.cuadraoDesignGallery.2d9c952af7", spanish: spanish))
                            .accessibilityIdentifier("gallery-empty-state")
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.60cf92b241", spanish: spanish)) {
                        CuadraoChartState(title: CuadraoCopy.text("copy.cuadraoDesignGallery.d9ec23ea81", spanish: spanish),
                            detail: CuadraoCopy.text("copy.cuadraoDesignGallery.25ab80246f", spanish: spanish))
                            .accessibilityIdentifier("gallery-empty-month")
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.08c8c7d7cc", spanish: spanish)) {
                        CuadraoChartState(title: CuadraoCopy.text("copy.cuadraoDesignGallery.a090e20844", spanish: spanish),
                            detail: CuadraoCopy.text("copy.cuadraoDesignGallery.5b746eec24", spanish: spanish))
                            .accessibilityIdentifier("gallery-unavailable-state")
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.eb1823e7e1", spanish: spanish)) {
                        CuadraoSkeleton(layout: .rows(3), motionEnabled: !previewReducedMotion, identifier: "gallery-skeleton-rows")
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.dae46ae8ef", spanish: spanish)) {
                        CuadraoSkeleton(layout: .home, motionEnabled: !previewReducedMotion, identifier: "gallery-skeleton-home")
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.07b4aced22", spanish: spanish)) {
                        Button(CuadraoCopy.text("copy.cuadraoDesignGallery.21a5574579", spanish: spanish)) {
                            toast = CuadraoToastMessage(text: CuadraoCopy.text("copy.cuadraoDesignGallery.a6208e9178", spanish: spanish),
                                actionTitle: CuadraoCopy.text("copy.connectedCuadraoHome.3ec51337bc", spanish: spanish), actionIdentifier: "gallery-toast-undo") { toast = nil }
                            CuadraoHaptics.impact()
                        }.frame(minHeight: 44).accessibilityIdentifier("gallery-toast-show")
                        HStack {
                            Button(CuadraoCopy.text("copy.cuadraoDesignGallery.aa9e02022c", spanish: spanish)) { CuadraoHaptics.success() }.frame(minHeight: 44)
                            Button(CuadraoCopy.text("copy.cuadraoDesignGallery.6e5a54ec82", spanish: spanish)) { CuadraoHaptics.warning() }.frame(minHeight: 44)
                            Button(CuadraoCopy.text("copy.cuadraoDesignGallery.8f1f42f679", spanish: spanish)) { CuadraoHaptics.selection() }.frame(minHeight: 44)
                        }
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.0e583d2da1", spanish: spanish)) {
                        CuadraoRetryState(message: "loop.error.connection", identifier: "gallery-retry-state",
                                          retryIdentifier: "gallery-retry-action") { retries += 1; CuadraoHaptics.selection() }
                        Text("\(retries)").font(CuadraoTypography.caption).foregroundStyle(.secondary).accessibilityIdentifier("gallery-retry-count")
                    }
                    sample(CuadraoCopy.text("copy.cuadraoDesignGallery.831ebe08b8", spanish: spanish)) {
                        CuadraoChartState(title: CuadraoCopy.text("copy.cuadraoDesignGallery.eade5627d9", spanish: spanish),
                            detail: CuadraoCopy.text("copy.cuadraoDesignGallery.0f8b6220f7", spanish: spanish), loading: true, motionEnabled: !previewReducedMotion)
                            .accessibilityIdentifier("gallery-loading-state")
                    }
                }.padding(24)
            }.scrollDismissesKeyboard(.interactively).background(WelcomePalette.background)
                .navigationTitle(CuadraoCopy.text("copy.cuadraoDesignGallery.b843c5b747", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(CuadraoCopy.text("copy.cuadraoAccountsCollection.f296f2cba3", spanish: spanish)) { dismiss() } } }
        }.preferredColorScheme(appearance.colorScheme)
            .onAppear { originalAppearance = appearance }
            .onDisappear { if let originalAppearance { appearance = originalAppearance } }
            .environment(\.dynamicTypeSize, largeText ? .accessibility2 : .large)
            .cuadraoToast($toast, spanish: spanish)
            .tint(WelcomePalette.pine)
    }
    private var controls: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker(CuadraoCopy.text("copy.cuadraoDesignGallery.98633ea3c0", spanish: spanish), selection: $spanish) { Text(CuadraoCopy.text("copy.cuadraoDesignGallery.bcca276cca", spanish: spanish)).tag(true); Text(CuadraoCopy.text("copy.cuadraoDesignGallery.058907014e", spanish: spanish)).tag(false) }
                .pickerStyle(.segmented).accessibilityIdentifier("gallery-language")
            Toggle(CuadraoCopy.text("copy.cuadraoAppearancePicker.d0713df468", spanish: spanish), isOn: dark).accessibilityIdentifier("gallery-dark")
            Toggle(CuadraoCopy.text("copy.cuadraoDesignGallery.fd5e10874f", spanish: spanish), isOn: $largeText).accessibilityIdentifier("gallery-large-text")
            Toggle(CuadraoCopy.text("copy.cuadraoDesignGallery.efbdd4a424", spanish: spanish), isOn: $previewReducedMotion).accessibilityIdentifier("gallery-reduce-motion")
        }.font(CuadraoTypography.supporting)
    }
    private var rowLabel: some View {
        Label(CuadraoCopy.text("copy.cuadraoDesignGallery.aa478547dc", spanish: spanish), systemImage: "basket")
            .font(CuadraoTypography.body)
    }
    private var rowAmount: some View { Text("DOP 1,250.00").font(CuadraoTypography.rowAmount) }
    private func sample<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(title).font(CuadraoTypography.caption).foregroundStyle(.secondary).accessibilityAddTraits(.isHeader)
            content()
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

#Preview("Cuadrao · Reference gallery") { CuadraoDesignGallery() }
