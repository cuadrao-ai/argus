import SwiftUI

enum CanvasFeedbackKind: String, CaseIterable, Identifiable {
    case general, bug, feature
    var id: Self { self }
    func title(_ spanish: Bool) -> String {
        switch self {
        case .general: CuadraoCopy.text("copy.cuadraoFeedbackPage.170d56d3fe", spanish: spanish)
        case .bug: CuadraoCopy.text("copy.cuadraoFeedbackPage.184bb939a5", spanish: spanish)
        case .feature: CuadraoCopy.text("copy.cuadraoFeedbackPage.4103100739", spanish: spanish)
        }
    }
}

struct CanvasFeedbackDraft: Equatable {
    var kind: CanvasFeedbackKind = .general
    var general = ""
    var feature = ""
    var bugTitle = ""
    var steps = ""
    var expected = ""
    var actual = ""

    var hasContent: Bool {
        let fields: [String]
        switch kind {
        case .general: fields = [general]
        case .feature: fields = [feature]
        case .bug: fields = [bugTitle, steps, expected, actual]
        }
        return fields.contains { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }
}

struct CuadraoFeedbackPage: View {
    @Binding var saved: CanvasFeedbackDraft
    let spanish: Bool
    @State private var draft: CanvasFeedbackDraft
    @State private var draftSaved = false

    init(saved: Binding<CanvasFeedbackDraft>, spanish: Bool) {
        _saved = saved; self.spanish = spanish
        _draft = State(initialValue: saved.wrappedValue)
    }

    var body: some View {
        Form {
            Section {
                LabeledContent(CuadraoCopy.text("copy.cuadraoFeedbackPage.574bdec2af", spanish: spanish)) {
                    CuadraoChoiceMenu(title: CuadraoCopy.text("copy.cuadraoFeedbackPage.4526febebf", spanish: spanish), selection: $draft.kind,
                        values: CanvasFeedbackKind.allCases, valueTitle: { $0.title(spanish) })
                        .accessibilityIdentifier("cuadrao.feedback.kind")
                }
            }.listRowBackground(CanvasSettingsStyle.surface)
            if draft.kind == .bug {
                Section {
                    field(CuadraoCopy.text("copy.cuadraoFeedbackPage.2a652ab658", spanish: spanish), text: $draft.bugTitle, limit: 100, id: "title")
                    field(CuadraoCopy.text("copy.cuadraoFeedbackPage.3f925f2c59", spanish: spanish), text: $draft.steps, limit: 1000, id: "steps")
                    field(CuadraoCopy.text("copy.cuadraoFeedbackPage.6271028868", spanish: spanish), text: $draft.expected, limit: 500, id: "expected")
                    field(CuadraoCopy.text("copy.cuadraoFeedbackPage.569bdc26ac", spanish: spanish), text: $draft.actual, limit: 500, id: "actual")
                } header: { Text(CuadraoCopy.text("copy.cuadraoFeedbackPage.6c2d8df5fa", spanish: spanish)) }
                    .listRowBackground(CanvasSettingsStyle.surface)
            } else {
                Section {
                    if draft.kind == .general {
                        field(CuadraoCopy.text("copy.cuadraoFeedbackPage.00c7565362", spanish: spanish), text: $draft.general, limit: 1000, id: "general")
                    } else {
                        field(CuadraoCopy.text("copy.cuadraoFeedbackPage.105bce0c0e", spanish: spanish), text: $draft.feature, limit: 1000, id: "feature")
                    }
                }.listRowBackground(CanvasSettingsStyle.surface)
            }
            Section {
                Button(CuadraoCopy.text("copy.cuadraoFeedbackPage.a070f191f6", spanish: spanish)) {
                    saved = draft; draftSaved = true
                }.disabled(!draft.hasContent).accessibilityIdentifier("cuadrao.feedback.save")
                if draftSaved {
                    Label(CuadraoCopy.text("copy.cuadraoFeedbackPage.d967611bff", spanish: spanish), systemImage: "checkmark")
                        .foregroundStyle(WelcomePalette.pine).font(.subheadline)
                        .accessibilityIdentifier("cuadrao.feedback.saved")
                }
            } footer: {
                Text(CuadraoCopy.text("copy.cuadraoFeedbackPage.6ffc2db721", spanish: spanish))
            }.listRowBackground(CanvasSettingsStyle.surface)
        }.onChange(of: draft) { _, _ in draftSaved = false }
            .scrollContentBackground(.hidden).background(WelcomePalette.background)
            .onAppear { draft = saved }
    }

    private func field(_ title: String, text: Binding<String>, limit: Int, id: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.subheadline).foregroundStyle(.secondary)
            TextField("", text: text, axis: .vertical).lineLimit(2...6)
                .accessibilityLabel(title)
                .accessibilityIdentifier("cuadrao.feedback.\(id)")
                .onChange(of: text.wrappedValue) { _, value in
                    if value.count > limit { text.wrappedValue = String(value.prefix(limit)) }
                }
            Text("\(text.wrappedValue.count)/\(limit)").font(.caption2).foregroundStyle(.tertiary)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }.padding(.vertical, 4).listRowBackground(CanvasSettingsStyle.surface)
    }
}
