import SwiftUI

@MainActor
struct AgeRangeObservationView<Content: View>: View {
    @StateObject private var observation: AgeRangeObservation
    @ViewBuilder let content: () -> Content

    init(observation: AgeRangeObservation? = nil, @ViewBuilder content: @escaping () -> Content) {
        _observation = StateObject(wrappedValue: observation ?? .shared)
        self.content = content
    }

    var body: some View {
        content().onAppear { observation.observe() }
    }
}
