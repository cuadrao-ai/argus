import Foundation

@MainActor
final class FakeAgeRangeChecker: AgeRangeChecking {
    enum Failure: Error { case synthetic }
    var required: AgeRangeRequirement
    var answer: DeclaredAgeAssessment
    var requirementFails = false
    var requestFails = false
    var requests = 0
    var requirements = 0
    init(_ required: AgeRangeRequirement, _ answer: DeclaredAgeAssessment = .adult) {
        self.required = required; self.answer = answer
    }
    func requirement() async throws -> AgeRangeRequirement {
        requirements += 1
        if requirementFails { throw Failure.synthetic }
        return required
    }
    func request() async throws -> DeclaredAgeAssessment {
        requests += 1
        if requestFails { throw Failure.synthetic }
        return answer
    }
}

@main
struct AgeConfirmationChecks {
    @MainActor
    static func main() async {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let confirmation = AgeConfirmation.recorded(at: now)
        for invalid in ["", "true", "18", "2026-10-17", "2026-10-17T12:00:00", "2036-01-01T00:00:00Z"] {
            precondition(AgeConfirmation(timestamp: invalid, now: now) == nil, "Reject invalid or future confirmation")
        }
        precondition(AgeConfirmation(timestamp: "2026-01-01T00:00:00-04:00", now: now) != nil)
        precondition(AgeConfirmation(timestamp: confirmation.timestamp, now: now) == confirmation)
        let checker = FakeAgeRangeChecker(.required)
        let missing = await AgeConfirmationPolicy.authorize(confirmation: nil, checker: checker)
        precondition(missing == .confirmationRequired && checker.requirements == 0 && checker.requests == 0)
        var cases = 1
        for requirement in [AgeRangeRequirement.unsupported, .optional, .required] {
            for assessment in [DeclaredAgeAssessment.adult, .under18, .notShared] {
                let checker = FakeAgeRangeChecker(requirement, assessment)
                let decision = await AgeConfirmationPolicy.authorize(confirmation: confirmation, checker: checker)
                let expected: AgeEntryDecision = requirement == .unsupported ? .allowed(confirmation)
                    : assessment == .under18 ? .under18
                    : assessment == .notShared && requirement == .required ? .sharingRequired : .allowed(confirmation)
                precondition(decision == expected)
                precondition(checker.requests == (requirement == .unsupported ? 0 : 1))
                cases += 1
            }
        }
        for required in [AgeRangeRequirement.optional, .required] {
            let checker = FakeAgeRangeChecker(required)
            checker.requestFails = true
            let decision = await AgeConfirmationPolicy.authorize(confirmation: confirmation, checker: checker)
            precondition(decision == (required == .required ? .unavailable : .allowed(confirmation)))
            checker.requirementFails = true
            let unknown = await AgeConfirmationPolicy.authorize(confirmation: confirmation, checker: checker)
            precondition(unknown == .unavailable)
            cases += 2
        }
        precondition(AgeConfirmationPolicy.assessment(lowerBound: nil, upperBound: 17) == .under18)
        precondition(AgeConfirmationPolicy.assessment(lowerBound: 18, upperBound: nil) == .adult)
        precondition(AgeConfirmationPolicy.assessment(lowerBound: nil, upperBound: nil) == .under18)
        precondition(AgeConfirmationPolicy.assessment(lowerBound: nil, upperBound: 18) == .under18)
        let terms = "https://legal.example.test/terminos"
        let config: [String: Any] = ["ARGUS_CUADRAO_TERMS_URL": terms, "ARGUS_CUADRAO_LEGAL_LINKS_ENABLED": "false"]
        precondition(CuadraoLegalURLs.ageGateTerms(info: config)?.absoluteString == terms)
        precondition(!CuadraoLegalURLs.configured(info: config).hasPages, "Under-18 terms exception does not enable signup legal links")
        for invalid in ["", "$(UNSET)", "http://legal.example.test/terms", "https://user:password@legal.example.test/terms"] {
            precondition(CuadraoLegalURLs.ageGateTerms(info: ["ARGUS_CUADRAO_TERMS_URL": invalid]) == nil)
        }
        let suite = "local.cuadrao.age-checks.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = AgeConfirmationStore(defaults: defaults)
        let underage = FakeAgeRangeChecker(.optional, .under18)
        let refused = AgeConfirmationModel(store: store, checker: underage)
        let entered = await refused.authorize(checked: true)
        precondition(!entered && refused.state == .under18 && store.confirmation == nil)
        underage.requestFails = true
        let retried = await refused.authorize(checked: true)
        precondition(!retried && refused.state == .under18 && underage.requests == 1)
        let required = FakeAgeRangeChecker(.required)
        required.requestFails = true
        let retrying = AgeConfirmationModel(store: store, checker: required)
        let failed = await retrying.authorize(checked: true)
        precondition(!failed && retrying.state == .unavailable && store.confirmation == nil)
        let acceptedAt = retrying.confirmation!
        required.requestFails = false
        let recovered = await retrying.authorize(checked: false)
        precondition(recovered && store.confirmation == acceptedAt, "Required Apple retries retain the checkbox timestamp without another checkbox")
        defaults.removeObject(forKey: AgeConfirmationStore.key)
        let olderOS = FakeAgeRangeChecker(.unsupported)
        let guest = AgeConfirmationModel(store: store, checker: olderOS)
        let absent = await guest.authorize(checked: false)
        precondition(!absent && store.confirmation == nil)
        let allowed = await guest.authorize(checked: true)
        precondition(allowed && olderOS.requests == 0)
        let original = store.confirmation!
        let conversion = AgeConfirmationModel(store: AgeConfirmationStore(defaults: defaults), checker: olderOS)
        let retained = await conversion.authorize(checked: false)
        precondition(retained && conversion.confirmation == original, "Guest conversion does not ask for another checkbox or replace timestamp")
        let storedKeys = defaults.dictionaryRepresentation().filter { $0.key.hasPrefix("cuadrao.age.") }
        precondition(storedKeys.count == 1 && storedKeys[AgeConfirmationStore.key] as? String == original.timestamp)
        print("Age confirmation passed: \(cases) policy cases, 7 timestamp checks, 4 bound checks, 7 entry and conversion checks")
    }
}
