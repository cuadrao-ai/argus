enum DeclaredAgeAssessment: String, Equatable, Sendable {
    case adult, under18, unknown, notShared, unsupported, unavailable

    init(lowerBound: Int?, upperBound: Int?) {
        if let upperBound, upperBound < 18 { self = .under18 }
        else if let lowerBound, lowerBound >= 18 { self = .adult }
        else { self = .unknown }
    }
}

@MainActor
protocol AgeRangeChecking {
    func request() async throws -> DeclaredAgeAssessment
}
