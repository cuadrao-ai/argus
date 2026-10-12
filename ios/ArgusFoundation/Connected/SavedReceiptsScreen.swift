import SwiftUI
import ArgusSession
import PDFKit

/// The saved-receipts list: view and delete. Saving happens from the + menu.
struct SavedReceiptsScreen: View {
    @ObservedObject var model: SavedReceiptsModel
    let spanish: Bool
    /// Continues a receipt the server is reading or has read. Without it, every row opens the file.
    var review: ((SavedDocument) -> Void)? = nil
    @State private var viewing: ViewedReceipt?
    @State private var deleting: SavedDocument?
    @State private var openFailed = false

    private var copy: SavedReceiptCopy { SavedReceiptCopy(spanish: spanish) }

    var body: some View {
        content
            .background(WelcomePalette.background)
            .navigationTitle(copy.title)
            .navigationBarTitleDisplayMode(.inline)
            .task { await model.load() }
            .refreshable { await model.load() }
            .sheet(item: $viewing) { receipt in SavedReceiptViewer(receipt: receipt, copy: copy) }
            .confirmationDialog(copy.deleteTitle, isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
                                titleVisibility: .visible, presenting: deleting) { document in
                Button(copy.delete, role: .destructive) { Task { await model.remove(document) } }
                    .accessibilityIdentifier("saved.receipts.delete.confirm")
                Button(copy.cancel, role: .cancel) {}
            } message: { _ in Text(copy.deleteMessage) }
            .alert(copy.couldNotOpen, isPresented: $openFailed) { Button(copy.done, role: .cancel) {} }
    }

    @ViewBuilder private var content: some View {
        if model.items.isEmpty {
            if model.loading {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if model.loadFailed {
                message(copy.couldNotLoad, retry: true)
            } else {
                message(copy.empty, retry: false)
            }
        } else {
            list
        }
    }

    private func message(_ text: String, retry: Bool) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "doc.viewfinder").font(.largeTitle).foregroundStyle(.secondary).accessibilityHidden(true)
            Text(text).font(CuadraoTypography.body).multilineTextAlignment(.center)
                .accessibilityIdentifier("saved.receipts.empty")
            if retry {
                Button(copy.retry) { Task { await model.load() } }.frame(minHeight: 44)
                    .accessibilityIdentifier("saved.receipts.retry")
            }
        }
        .padding(32).frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var list: some View {
        List {
            ForEach(model.items) { document in
                Button { select(document) } label: { row(document) }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("saved.receipts.row." + document.id)
                    .accessibilityAction(named: Text(copy.delete)) { deleting = document }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) { deleting = document } label: { Label(copy.delete, systemImage: "trash") }
                    }
                    .contextMenu {
                        Button { open(document) } label: { Label(copy.view, systemImage: "doc.text.magnifyingglass") }
                        Button(role: .destructive) { deleting = document } label: { Label(copy.delete, systemImage: "trash") }
                    }
                    .onAppear { if document.id == model.items.last?.id, model.hasMore { Task { await model.loadMore() } } }
            }
        }
        .listStyle(.plain)
        .accessibilityIdentifier("saved.receipts.list")
    }

    private func row(_ document: SavedDocument) -> some View {
        HStack(spacing: 14) {
            Image(systemName: document.mediaType == "application/pdf" ? "doc.text" : "photo")
                .font(.title3).foregroundStyle(WelcomePalette.pine)
                .frame(width: 40, height: 40).background(WelcomePalette.pine.opacity(0.1), in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(document.filename).font(CuadraoTypography.body).lineLimit(2)
                Text(detail(document)).font(CuadraoTypography.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if model.removing == document.id { ProgressView() }
        }
        .frame(minHeight: 56).contentShape(Rectangle())
    }

    private func detail(_ document: SavedDocument) -> String {
        let size = ByteCountFormatter.string(fromByteCount: Int64(document.sizeBytes), countStyle: .file)
        guard let created = document.created else { return size }
        let date = created.formatted(.dateTime.day().month(.abbreviated).year().locale(Locale(identifier: spanish ? "es_DO" : "en_US")))
        return size + " · " + date
    }

    private func select(_ document: SavedDocument) {
        if let review, document.status != "saved" { review(document) } else { open(document) }
    }

    private func open(_ document: SavedDocument) {
        Task {
            if let data = await model.source(of: document) { viewing = ViewedReceipt(document: document, data: data) }
            else { openFailed = true }
        }
    }
}

struct ViewedReceipt: Identifiable {
    let document: SavedDocument
    let data: Data
    var id: String { document.id }
}

struct SavedReceiptViewer: View {
    let receipt: ViewedReceipt
    let copy: SavedReceiptCopy
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if receipt.document.mediaType == "application/pdf" {
                    SavedReceiptPDF(data: receipt.data)
                } else if let image = UIImage(data: receipt.data) {
                    ScrollView { Image(uiImage: image).resizable().scaledToFit().accessibilityLabel(receipt.document.filename) }
                } else {
                    Text(copy.couldNotOpen).padding(32)
                }
            }
            .navigationTitle(receipt.document.filename).navigationBarTitleDisplayMode(.inline)
            .toolbar { CuadraoDoneToolbar(title: copy.done) { dismiss() } }
        }
        .tint(WelcomePalette.pine)
    }
}

private struct SavedReceiptPDF: UIViewRepresentable {
    let data: Data
    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.document = PDFDocument(data: data)
        return view
    }
    func updateUIView(_ view: PDFView, context: Context) {}
}

/// The answer after saving, as an alert, and a quiet indicator while a file is being saved.
private struct SavedReceiptOutcomeAlert: ViewModifier {
    @ObservedObject var model: SavedReceiptsModel
    let spanish: Bool
    private var copy: SavedReceiptCopy { SavedReceiptCopy(spanish: spanish) }

    func body(content: Content) -> some View {
        content
            .overlay {
                if model.saving {
                    ProgressView(copy.saving)
                        .padding(20).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
                        .accessibilityIdentifier("saved.receipts.saving")
                }
            }
            .alert(title, isPresented: Binding(get: { model.outcome != nil }, set: { if !$0 { model.outcome = nil } })) {
                if case .failed(.couldNotSave)? = model.outcome, model.canRetry {
                    Button(copy.retry) { Task { await model.retry() } }.accessibilityIdentifier("saved.receipts.retry.save")
                    Button(copy.cancel, role: .cancel) { model.discardFailedFiles() }
                } else {
                    Button(copy.done, role: .cancel) { model.discardFailedFiles() }.accessibilityIdentifier("saved.receipts.outcome.done")
                }
            } message: {
                if case .saved? = model.outcome { Text(copy.savedDetail) }
            }
    }

    private var title: String {
        switch model.outcome {
        case .saved?: copy.savedTitle
        case .alreadySaved?: copy.alreadySaved
        case .failed(let failure)?: copy.failure(failure)
        case nil: ""
        }
    }
}

extension View {
    @ViewBuilder
    func savedReceiptOutcome(_ model: SavedReceiptsModel?, spanish: Bool) -> some View {
        if let model { modifier(SavedReceiptOutcomeAlert(model: model, spanish: spanish)) } else { self }
    }
}
