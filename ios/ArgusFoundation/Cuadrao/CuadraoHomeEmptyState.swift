import SwiftUI

// In-memory design fixtures. No invitations or membership changes leave this canvas.
enum CanvasHouseholdState {
    case alone, invitation(CanvasHouseholdInvitation), joined(String)
}

struct CuadraoHomeEmptyState: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    let addAccount: () -> Void
    let household: () -> Void
    private var shared: Bool { data.selectedSpace.kind == .household }

    var body: some View {
        if shared {
            VStack(alignment: .leading, spacing: 28) {
                CuadraoChartState(title: CuadraoCopy.text("copy.cuadraoHomeEmptyState.c598130645", spanish: spanish),
                    detail: CuadraoCopy.text("copy.cuadraoHomeEmptyState.d5472c73fa", spanish: spanish))
                RegistrationButton(title: CuadraoCopy.text("copy.cuadraoHomeEmptyState.c4386d1150", spanish: spanish), action: addAccount)
                if case .alone = data.household {
                    secondary(CuadraoCopy.text("copy.cuadraoHomeEmptyState.d9987908d0", spanish: spanish), action: household)
                } else {
                    secondary(CuadraoCopy.text("copy.cuadraoHomeEmptyState.bede691c92", spanish: spanish), action: household)
                }
            }.padding(.top, 16).frame(maxWidth: .infinity, alignment: .leading)
        } else {
            CuadraoPersonalAccountsEmpty(spanish: spanish, addAccount: addAccount)
        }
    }
    private func secondary(_ title: String, action: @escaping () -> Void) -> some View {
        Button(title, action: action).font(.subheadline.weight(.medium))
            .frame(maxWidth: .infinity, minHeight: 44)
    }
}

struct CuadraoPersonalAccountsEmpty: View {
    let spanish: Bool
    let addAccount: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            CuadraoChartState(title: CuadraoCopy.text("copy.cuadraoHomeEmptyState.deb93bf23e", spanish: spanish),
                detail: CuadraoCopy.text("copy.cuadraoHomeEmptyState.9ba4d39d99", spanish: spanish))
            RegistrationButton(title: CuadraoCopy.text("copy.connectedCuadraoHome.10d1d9ce3f", spanish: spanish), action: addAccount)
                .accessibilityIdentifier("accounts.add")
        }.padding(.top, 16).frame(maxWidth: .infinity, alignment: .leading)
    }
}
