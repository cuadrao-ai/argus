import Foundation

@MainActor
struct AppleAgeRangeChecker: AgeRangeChecking {
    func request() async throws -> DeclaredAgeAssessment { .unsupported }
}

@MainActor
final class FakeAgeRangeChecker: AgeRangeChecking {
    var answer: DeclaredAgeAssessment
    var failure: Error?
    var requests = 0

    init(_ answer: DeclaredAgeAssessment) { self.answer = answer }

    func request() async throws -> DeclaredAgeAssessment {
        requests += 1
        if let failure { throw failure }
        return answer
    }
}

@MainActor
final class PendingAgeRangeChecker: AgeRangeChecking {
    var pending: [CheckedContinuation<DeclaredAgeAssessment, Never>] = []
    func request() async throws -> DeclaredAgeAssessment {
        await withCheckedContinuation { pending.append($0) }
    }
    func waitForRequests(_ count: Int) async {
        for _ in 0..<1000 {
            if pending.count == count { return }
            await Task.yield()
        }
        preconditionFailure("Native request did not start")
    }
}

@main
struct AgeConfirmationChecks {
    @MainActor
    static func main() async {
        for result in [DeclaredAgeAssessment.adult, .under18, .unknown, .notShared, .unsupported, .unavailable] {
            var recorded: [DeclaredAgeAssessment] = []
            let checker = FakeAgeRangeChecker(result)
            let observation = AgeRangeObservation(checker: checker, record: { recorded.append($0) })
            await observation.observe()?.value
            precondition(observation.assessment == result && recorded == [result])
            await observation.observe()?.value
            precondition(checker.requests == 1, "View redraw must not repeat the system prompt")
        }
        let error = FakeAgeRangeChecker(.adult)
        error.failure = NSError(domain: "synthetic", code: 1)
        var failures: [DeclaredAgeAssessment] = []
        let failed = AgeRangeObservation(checker: error, record: { failures.append($0) })
        await failed.observe()?.value
        precondition(failed.assessment == .unavailable && failures == [.unavailable])

        let cancelled = FakeAgeRangeChecker(.adult)
        cancelled.failure = CancellationError()
        var cancelledResults: [DeclaredAgeAssessment] = []
        let interrupted = AgeRangeObservation(checker: cancelled, record: { cancelledResults.append($0) })
        await interrupted.observe()?.value
        precondition(interrupted.assessment == nil && cancelledResults.isEmpty)
        cancelled.failure = nil
        await interrupted.observe()?.value
        precondition(interrupted.assessment == .adult && cancelled.requests == 2 && cancelledResults == [.adult])

        let checker = PendingAgeRangeChecker()
        var recorded: [DeclaredAgeAssessment] = []
        let pending = AgeRangeObservation(checker: checker, record: { recorded.append($0) })
        let first = pending.observe()!
        await checker.waitForRequests(1)
        _ = pending.observe()
        precondition(checker.pending.count == 1 && pending.assessment == nil, "Pending request is deduplicated without an entry decision")
        pending.cancel()
        let second = pending.observe()!
        await checker.waitForRequests(2)
        checker.pending[1].resume(returning: .notShared)
        await second.value
        checker.pending[0].resume(returning: .under18)
        await first.value
        precondition(pending.assessment == .notShared && recorded == [.notShared], "Stale cancelled task must not overwrite or log the new observation")

        precondition(DeclaredAgeAssessment(lowerBound: nil, upperBound: 17) == .under18)
        precondition(DeclaredAgeAssessment(lowerBound: 18, upperBound: nil) == .adult)
        precondition(DeclaredAgeAssessment(lowerBound: nil, upperBound: nil) == .unknown)
        precondition(DeclaredAgeAssessment(lowerBound: 13, upperBound: 20) == .unknown)
        print("Age observation passed: 6 outcomes, error, cancellation and retry, pending deduplication, stale completion, 4 coarse ranges")
    }
}
