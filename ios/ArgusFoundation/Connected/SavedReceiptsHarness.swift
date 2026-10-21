#if DEBUG
import ArgusSession
import SwiftUI

/// `--saved-receipts-harness`: the connected saved-receipts list alone, against the sample files and a synthetic
/// session, so its swipe actions can be checked without signing in.
struct SavedReceiptsHarness: View {
    @StateObject private var model: SavedReceiptsModel
    @Environment(\.locale) private var locale

    init() {
        let model = SavedReceiptsModel(transport: SampleSavedReceiptsTransport(), currentSession: { SavedReceiptsHarness.session })
        model.bind(SavedReceiptsHarness.session)
        _model = StateObject(wrappedValue: model)
    }

    nonisolated private static let session = SessionSnapshot(
        phase: .authenticated, profile: try? JSONDecoder().decode(SessionProfile.self, from: Data(#"{"id":"harness"}"#.utf8)), revision: 1)

    var body: some View {
        NavigationStack {
            SavedReceiptsScreen(model: model, spanish: CuadraoCopy.isSpanish())
        }.tint(WelcomePalette.pine)
    }
}
#endif
