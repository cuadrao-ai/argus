import SwiftUI

/// The one empty state: Plan palette art, one line of title, one line of help and at most one action.
struct CuadraoEmptyView: View {
    let title: String
    var detail: String?
    var look: CanvasPlanLook = .coast
    var actionTitle: String?
    var action: (() -> Void)?
    var identifier: String?
    var actionIdentifier: String?

    var body: some View {
        VStack(spacing: 16) {
            PlanLandscape(look: look).frame(width: 112, height: 96).accessibilityHidden(true)
            VStack(spacing: 6) {
                Text(title).font(CuadraoTypography.section).multilineTextAlignment(.center)
                    .accessibilityIdentifier(identifier ?? "")
                if let detail {
                    Text(detail).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
            }
            if let actionTitle, let action {
                Button(action: action) {
                    Text(actionTitle).font(.subheadline.weight(.semibold)).foregroundStyle(WelcomePalette.pine)
                        .padding(.horizontal, 20).frame(minHeight: 44)
                        .overlay { Capsule().stroke(WelcomePalette.border) }.contentShape(Capsule())
                }.buttonStyle(.plain).accessibilityIdentifier(actionIdentifier ?? "")
            }
        }.frame(maxWidth: .infinity).padding(.vertical, 24)
    }
}
