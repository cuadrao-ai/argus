import SwiftUI

struct CuadraoPlanDetailDisplay {
    let name: String
    let space: String
    let look: CanvasPlanLook
    let amount: String
    let annotation: String
    var amountIdentifier: String? = nil
}

struct CuadraoPlanDetailPage<Content: View>: View {
    var bottomSpace: CGFloat = 90
    var scroll: FinancialScrollContext?
    @ViewBuilder let content: () -> Content

    var body: some View {
        Group {
            if let scroll {
                FinancialRestoringScrollView(context: scroll) { pageContent }.id(scroll.id)
            } else {
                ScrollView { pageContent }
            }
        }
        .background(WelcomePalette.background).cuadraoSoftScrollEdges()
    }

    private var pageContent: some View {
        VStack(alignment: .leading, spacing: 20) {
            content()
        }.padding(24).padding(.bottom, bottomSpace)
    }
}

struct CuadraoPlanDetailHeading<Status: View>: View {
    let display: CuadraoPlanDetailDisplay
    @ViewBuilder let status: () -> Status

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(display.space).font(.caption).foregroundStyle(.secondary)
            HStack(alignment: .center, spacing: 16) {
                Text(display.name).font(CuadraoTypography.feature).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                PlanLandscape(look: display.look).frame(width: 70, height: 76)
            }
            HStack {
                Text(display.amount).font(CuadraoTypography.secondaryAmount)
                    .accessibilityIdentifier(display.amountIdentifier ?? "")
                Text(display.annotation).font(.caption).foregroundStyle(.secondary)
            }
            status()
        }
    }
}

struct CuadraoPlanDetailFacts<Content: View>: View {
    let spanish: Bool
    @ViewBuilder let content: () -> Content

    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 16) {
                content()
            }.font(.subheadline).padding(.top, 16)
        } label: {
            Text(CuadraoCopy.text("copy.cuadraoPlanDetailPresentation.02d6d9b267", spanish: spanish)).font(.subheadline.weight(.medium))
        }
    }
}

struct CuadraoPlanDetailOptions<Content: View>: View {
    let spanish: Bool
    @ViewBuilder let content: () -> Content

    var body: some View {
        Menu(content: content) {
            Image(systemName: "ellipsis").frame(width: 44, height: 44)
        }
        .accessibilityLabel(CuadraoCopy.text("copy.cuadraoPlanDetailPresentation.22bf9418ef", spanish: spanish))
        .accessibilityIdentifier("plan-detail-options")
    }
}
