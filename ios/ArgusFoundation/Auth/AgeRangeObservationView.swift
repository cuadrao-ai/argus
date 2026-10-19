import SwiftUI

@MainActor
struct AgeRangeObservationView<Content: View>: View {
    @StateObject private var observation: AgeRangeObservation
    @ViewBuilder let content: () -> Content

    init(observation: AgeRangeObservation? = nil, @ViewBuilder content: @escaping () -> Content) {
        #if DEBUG
        let fixture = AgeConfirmationHarness.legalEntryObservation()
        #else
        let fixture: AgeRangeObservation? = nil
        #endif
        _observation = StateObject(wrappedValue: observation ?? fixture ?? .shared)
        self.content = content
    }

    var body: some View {
        content().onAppear { observation.observe() }
    }
}
