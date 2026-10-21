import SwiftUI
import CoreImage.CIFilterBuiltins
import ArgusSession

struct ReleaseInvitationShare {
    let url: URL?
    var code: String? = nil
    var expiresAt: Date? = nil
    var testFlightURL: URL? = nil
}

struct ReleaseInvitationShareCard: View {
    let invitation: ReleaseInvitationShare
    let spanish: Bool
    var identifier = "release.invitation"

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let url = invitation.url {
                ReleaseInvitationQRCode(url: url, spanish: spanish)
                    .frame(maxWidth: .infinity)
                    .accessibilityIdentifier(identifier + ".qr")
            }
            if let code = invitation.code {
                VStack(alignment: .leading, spacing: 8) {
                    Text(CuadraoCopy.text("copy.releaseInvitationShare.0da28c8201", spanish: spanish))
                        .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    Text(code).font(.system(.title2, design: .monospaced))
                        .textSelection(.enabled)
                        .accessibilityIdentifier(identifier + ".code")
                }
            }
            if let url = invitation.url {
                Text(url.absoluteString).font(CuadraoTypography.caption)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(identifier + ".link")
            }
            if let expiresAt = invitation.expiresAt {
                Text(CuadraoCopy.text("copy.releaseInvitationShare.d6a57a460f", spanish: spanish, String(describing: expiresAt.formatted(date: .abbreviated, time: .shortened))))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
            if let item = invitation.url?.absoluteString ?? invitation.code {
                ShareLink(item: item) {
                    Label(CuadraoCopy.text("copy.cuadraoHouseholdSheet.3e59d3aca8", spanish: spanish), systemImage: "square.and.arrow.up")
                        .frame(maxWidth: .infinity, minHeight: 48).modifier(ReleaseProminentLabel())
                }
                .buttonStyle(.borderedProminent).tint(WelcomePalette.pine)
                .accessibilityIdentifier(identifier + ".share")
            }
            if let testFlightURL = invitation.testFlightURL {
                Link(destination: testFlightURL) {
                    Text(CuadraoCopy.text("copy.releaseInvitationShare.b0eb75ce95", spanish: spanish)).frame(minHeight: 44)
                }.accessibilityIdentifier(identifier + ".testFlight")
                Text(CuadraoCopy.text("copy.releaseInvitationShare.2be7c75fbd", spanish: spanish))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
            Text(CuadraoCopy.text("copy.releaseInvitationShare.87cd57b6e7", spanish: spanish))
                .font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }
        .foregroundStyle(WelcomePalette.ink)
    }
}

struct ReleaseInvitationQRCode: View {
    private let image: UIImage?
    let spanish: Bool

    init(url: URL, spanish: Bool) {
        self.spanish = spanish
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(url.absoluteString.utf8)
        filter.correctionLevel = "M"
        if let code = filter.outputImage {
            // Core Image emits one pixel per module. Preserve four white modules
            // on every edge before scaling; decoration never enters this region.
            let extent = code.extent.insetBy(dx: -4, dy: -4)
            let white = CIImage(color: CIColor(red: 1, green: 1, blue: 1)).cropped(to: extent)
            let padded = code.composited(over: white).cropped(to: extent)
                .transformed(by: CGAffineTransform(scaleX: 8, y: 8))
            image = CIContext().createCGImage(padded, from: padded.extent).map { UIImage(cgImage: $0) }
        } else { image = nil }
    }

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image).interpolation(.none).resizable().scaledToFit()
                    .frame(maxWidth: 240).background(.white)
                    .accessibilityLabel(CuadraoCopy.text("copy.releaseInvitationShare.6992ff98b5", spanish: spanish))
            } else {
                Text(CuadraoCopy.text("copy.releaseInvitationShare.5f4aad07ab", spanish: spanish))
                    .font(CuadraoTypography.supporting)
            }
        }
    }
}

struct HouseholdInvitationShareView: View {
    let invitation: HouseholdInvitation
    let spanish: Bool

    var body: some View {
        if let url = invitation.link.flatMap(URL.init(string:)) ?? invitation.token.flatMap({ URL(string: "argus-household://invite#" + $0) }) {
            VStack(alignment: .leading, spacing: 16) {
                Text(CuadraoCopy.text("copy.releaseInvitationShare.09b59dcc3a", spanish: spanish))
                    .font(CuadraoTypography.section)
                Text("household.consent").font(CuadraoTypography.supporting)
                Text(CuadraoCopy.text("copy.releaseInvitationShare.2b864f2fbf", spanish: spanish))
                    .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                ReleaseInvitationShareCard(invitation: ReleaseInvitationShare(url: url, code: invitation.code,
                                                                              expiresAt: InvitationDates.date(invitation.expiresAt)),
                                           spanish: spanish, identifier: "household.invite")
                Text("household.invitationPrepared").font(CuadraoTypography.caption)
            }.padding(.vertical, 8)
        } else {
            Text("household.linkUnavailable").font(.footnote).accessibilityIdentifier("household.invite.lost")
        }
    }
}

/// Prominent labels sit on the pine fill, so they take the on-accent ink instead of the page ink.
struct ReleaseProminentLabel: ViewModifier {
    @Environment(\.isEnabled) private var enabled
    func body(content: Content) -> some View {
        content.foregroundStyle(enabled ? WelcomePalette.onAccent : WelcomePalette.disabledInk)
    }
}

struct ReleaseInvitationPage<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                CuadraoBrand().frame(maxWidth: .infinity).accessibilityHidden(true)
                WelcomeSquares().frame(maxWidth: .infinity).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 12) {
                    Text(title).font(CuadraoTypography.screen)
                    Text(subtitle).font(CuadraoTypography.body).foregroundStyle(.secondary)
                }
                content()
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(24).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }
        .background(WelcomePalette.background)
        .foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)
        .scrollDismissesKeyboard(.interactively)
    }
}
