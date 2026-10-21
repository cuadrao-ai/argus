import SwiftUI

struct CuadraoPlanHeader: View {
    let spanish: Bool
    let createTitle: String
    var canCreate = true
    var createIdentifier = "plan-create"
    /// The Preview's hold-to-reset menu sits on the title only, never on the create button.
    var titleMenu: (() -> AnyView)? = nil
    let create: () -> Void

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 6) {
                let title = Text(CuadraoCopy.text("copy.cuadraoPlanDisplay.407f9183d7", spanish: spanish)).font(CuadraoTypography.screen)
                    .accessibilityIdentifier("plan-heading")
                if let titleMenu { title.contextMenu { titleMenu() } } else { title }
            }
            Spacer()
            Button(action: create) {
                Image(systemName: "plus").font(.system(size: 20, weight: .medium))
                    .frame(width: 44, height: 44).background(WelcomePalette.sage, in: Circle())
            }.accessibilityLabel(createTitle).accessibilityIdentifier(createIdentifier)
                .disabled(!canCreate)
        }
    }
}

struct CuadraoPlanAudiencePicker: View {
    let spanish: Bool
    @Binding var together: Bool

    var body: some View {
        Picker(CuadraoCopy.text("copy.cuadraoDesignGallery.daeb973c09", spanish: spanish), selection: $together) {
            Text(CuadraoCopy.text("copy.cuadraoPlanDisplay.21d78618d0", spanish: spanish)).tag(false)
            Text(CuadraoCopy.text("copy.cuadraoPlanDisplay.f85130a375", spanish: spanish)).tag(true)
        }.pickerStyle(.segmented).accessibilityIdentifier("plan-audience")
    }
}

struct CuadraoPlanForecastHeading<Scope: View>: View {
    let period: String
    @ViewBuilder let scope: () -> Scope

    var body: some View {
        HStack(spacing: 8) {
            Text(period).font(CuadraoTypography.supporting).foregroundStyle(.secondary)
            Spacer()
            scope()
        }
    }
}

struct CuadraoPlanForecastValue: View {
    let title: String
    let amount: String
    let identifier: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.subheadline).foregroundStyle(.secondary)
            Text(amount).font(CuadraoTypography.amount).monospacedDigit()
                .contentTransition(.numericText()).minimumScaleFactor(0.65).lineLimit(1)
                .accessibilityIdentifier(identifier)
        }
    }
}

struct CuadraoPlanCardDisplay {
    let name: String
    let space: String
    let look: CanvasPlanLook
    let amount: String
    var annotation: String? = nil
    var progress: Double? = nil
    let detail: String
    var notice: String? = nil
}

struct CuadraoPlanCard: View {
    let display: CuadraoPlanCardDisplay

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(display.space).font(.caption).foregroundStyle(.secondary)
                    Text(display.name).font(CuadraoTypography.section).foregroundStyle(WelcomePalette.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                PlanLandscape(look: display.look).frame(width: 84, height: 84)
            }
            VStack(alignment: .leading, spacing: 9) {
                HStack(alignment: .firstTextBaseline) {
                    Text(display.amount).font(CuadraoTypography.secondaryAmount)
                    Spacer(minLength: 8)
                    if let annotation = display.annotation {
                        Text(annotation).font(.caption).foregroundStyle(.secondary)
                    }
                }
                if let progress = display.progress {
                    GeometryReader { g in
                        Capsule().fill(display.look.color.opacity(0.1))
                            .overlay(alignment: .leading) {
                                Capsule().fill(display.look.color).frame(width: max(0, g.size.width * progress))
                            }
                    }.frame(height: 4).accessibilityHidden(true)
                }
                Text(display.detail).font(.caption).foregroundStyle(.secondary)
                if let notice = display.notice {
                    Text(notice).font(.caption).foregroundStyle(.secondary)
                }
            }
        }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
            .background(display.look.color.opacity(0.065), in: RoundedRectangle(cornerRadius: 28))
            .contentShape(RoundedRectangle(cornerRadius: 28))
    }
}
