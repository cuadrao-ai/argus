import SwiftUI

/// Grey blocks in the footprint of the real content while a request is pending.
/// A settled empty state is not a loading state and never uses this view.
struct CuadraoSkeleton: View {
    enum Layout {
        case rows(Int)
        /// A balance headline, a chart area and a few rows, as on Home.
        case home
        case card
    }

    let layout: Layout
    var motionEnabled = true
    var identifier = "cuadrao.skeleton"

    var body: some View {
        content
            .modifier(CuadraoShimmer(motionEnabled: motionEnabled))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(NSLocalizedString("skeleton.loading", comment: ""))
            .accessibilityAddTraits(.updatesFrequently)
            .accessibilityIdentifier(identifier)
    }

    @ViewBuilder private var content: some View {
        switch layout {
        case .rows(let count):
            VStack(spacing: 20) { ForEach(0..<count, id: \.self) { _ in CuadraoSkeletonRow() } }
        case .home:
            VStack(alignment: .leading, spacing: 28) {
                VStack(alignment: .leading, spacing: 12) {
                    CuadraoSkeletonBlock(width: 120, height: 14)
                    CuadraoSkeletonBlock(width: 220, height: 40, corner: 10)
                }
                CuadraoSkeletonBlock(height: 150, corner: 16)
                VStack(spacing: 20) { ForEach(0..<4, id: \.self) { _ in CuadraoSkeletonRow() } }
            }
        case .card:
            VStack(alignment: .leading, spacing: 12) {
                CuadraoSkeletonBlock(width: 140, height: 14)
                CuadraoSkeletonBlock(height: 14)
                CuadraoSkeletonBlock(width: 180, height: 14)
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 18))
        }
    }
}

struct CuadraoSkeletonBlock: View {
    var width: CGFloat?
    var height: CGFloat = 14
    var corner: CGFloat = 6
    var body: some View {
        RoundedRectangle(cornerRadius: corner).fill(WelcomePalette.ink.opacity(0.08))
            .frame(width: width, height: height)
            .frame(maxWidth: width == nil ? .infinity : nil, alignment: .leading)
    }
}

/// An icon, two lines and an amount: the shape of a movement or account row.
struct CuadraoSkeletonRow: View {
    var body: some View {
        HStack(spacing: 14) {
            Circle().fill(WelcomePalette.ink.opacity(0.08)).frame(width: 40, height: 40)
            VStack(alignment: .leading, spacing: 8) {
                CuadraoSkeletonBlock(width: 150, height: 14)
                CuadraoSkeletonBlock(width: 100, height: 11)
            }
            Spacer(minLength: 12)
            CuadraoSkeletonBlock(width: 70, height: 14)
        }
    }
}

/// A light band that crosses the blocks. Reduce Motion, or a preview that turns motion off, keeps them still.
private struct CuadraoShimmer: ViewModifier {
    let motionEnabled: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var phase: CGFloat = -0.6

    private var moving: Bool { motionEnabled && !reduceMotion }

    func body(content: Content) -> some View {
        content
            .overlay {
                if moving {
                    GeometryReader { proxy in
                        LinearGradient(colors: [.clear, WelcomePalette.surface.opacity(0.7), .clear],
                                       startPoint: .leading, endPoint: .trailing)
                            .frame(width: proxy.size.width * 0.6)
                            .offset(x: proxy.size.width * phase)
                    }.mask(content).allowsHitTesting(false)
                }
            }
            .task(id: moving) {
                phase = -0.6
                if moving { withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) { phase = 1 } }
            }
    }
}
