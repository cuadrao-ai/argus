import SwiftUI

struct CanvasChatAttachmentChip: View {
    let item: CanvasChatAttachment
    var spanish = true
    var remove: (() -> Void)? = nil
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: item.symbol).foregroundStyle(WelcomePalette.pine)
            Text(item.name).font(.footnote).lineLimit(2)
            if let remove {
                Button(action: remove) { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .accessibilityLabel(Text(item.name + " · " + (CuadraoCopy.text("copy.cuadraoChatAnswer.1b73d18e75", spanish: spanish))))
            }
        }.padding(.leading, 12).padding(.trailing, remove == nil ? 12 : 0).padding(.vertical, remove == nil ? 12 : 0)
            .background(WelcomePalette.background, in: RoundedRectangle(cornerRadius: 14))
            .overlay { RoundedRectangle(cornerRadius: 14).stroke(WelcomePalette.separator, lineWidth: 1) }
    }
}

enum CanvasChatCalculation {
    static let monthly = 3_000
    static let months = 6
    static var total: Int { monthly * months }
    static func amount(_ value: Int) -> String { value.formatted(.number.locale(Locale(identifier: "en_US"))) }
}

struct CuadraoChatAnswer: View {
    let turn: CanvasChatTurn
    let spanish: Bool
    let showSources: () -> Void
    let showDetails: () -> Void
    @State private var copied = false
    @State private var feedback = false
    private var es: Bool { spanish }
    private var answer: String {
        switch turn.example {
        case .savings:
            CuadraoCopy.text("copy.cuadraoChatAnswer.8076376dc7", spanish: es, String(describing: CanvasChatCalculation.amount(CanvasChatCalculation.total)))
        case .certificate:
            CuadraoCopy.text("copy.cuadraoChatAnswer.d945b28e0e", spanish: es)
        case .document:
            CuadraoCopy.text("copy.cuadraoChatAnswer.67800d5eda", spanish: es)
        case nil:
            CuadraoCopy.text("copy.cuadraoChatAnswer.f715280c85", spanish: es)
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(CuadraoCopy.text("copy.cuadraoChatAnswer.ea3e774390", spanish: es))
                .font(.system(size: 10, weight: .medium)).tracking(1.3).foregroundStyle(.secondary)
            Text(answer).font(.body).lineSpacing(5).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            if turn.example == .savings {
                Button(action: showDetails) {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(CuadraoCopy.text("copy.cuadraoChatAnswer.247a9b1d27", spanish: es)).font(.subheadline).foregroundStyle(.secondary)
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("DOP").font(.subheadline).foregroundStyle(.secondary)
                            Text(CanvasChatCalculation.amount(CanvasChatCalculation.total)).font(CuadraoTypography.amount).monospacedDigit()
                        }
                        Divider()
                        HStack {
                            Text(CuadraoCopy.text("copy.cuadraoChatAnswer.fa706248ef", spanish: es))
                            Spacer(); Image(systemName: "chevron.right").font(.caption)
                        }.font(.subheadline)
                    }.padding(20).background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 20))
                }.buttonStyle(.plain).accessibilityIdentifier("chat-calculation")
                Text(CuadraoCopy.text("copy.cuadraoChatAnswer.a97b0ee59b", spanish: es))
                    .font(.footnote).foregroundStyle(.secondary)
            }
            if turn.example == .certificate {
                explanation(CuadraoCopy.text("copy.cuadraoChatAnswer.952943dfd0", spanish: es), CuadraoCopy.text("copy.cuadraoChatAnswer.6b63ba3f15", spanish: es))
                explanation(CuadraoCopy.text("copy.cuadraoChatAnswer.739b860862", spanish: es), CuadraoCopy.text("copy.cuadraoChatAnswer.7fe8d78a25", spanish: es))
                explanation(CuadraoCopy.text("copy.cuadraoChatAnswer.a7bef519cb", spanish: es), CuadraoCopy.text("copy.cuadraoChatAnswer.9107177fe0", spanish: es))
                Button(action: showSources) {
                    Label(CuadraoCopy.text("copy.cuadraoChatAnswer.98180ee4aa", spanish: es), systemImage: "info.circle")
                        .font(.footnote).frame(minHeight: 44)
                }
            }
            HStack(spacing: 4) {
                Button { UIPasteboard.general.string = answer; copied = true } label: {
                    Image(systemName: copied ? "checkmark" : "doc.on.doc").frame(width: 44, height: 44)
                }.accessibilityLabel(CuadraoCopy.text("copy.cuadraoChatAnswer.016c5c4429", spanish: es))
                Button { feedback = true } label: { Image(systemName: "hand.thumbsdown").frame(width: 44, height: 44) }
                    .accessibilityLabel(CuadraoCopy.text("copy.cuadraoChatAnswer.b977187eda", spanish: es))
                Spacer()
            }.font(.system(size: 15)).foregroundStyle(.secondary)
        }
        .alert(CuadraoCopy.text("copy.cuadraoChatAnswer.1b153643ac", spanish: es), isPresented: $feedback) {
            Button(CuadraoCopy.text("copy.cuadraoChatAnswer.bd6b05a681", spanish: es), role: .cancel) { }
        } message: {
            Text(CuadraoCopy.text("copy.cuadraoChatAnswer.4d9494226a", spanish: es))
        }
    }
    private func explanation(_ title: String, _ detail: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.body.weight(.semibold))
            Text(detail).font(.body).lineSpacing(4)
        }
    }
}
