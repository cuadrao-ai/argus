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
            let observedAt = Date(timeIntervalSince1970: 1767225600)
            var clockReads = 0
            let observation = AgeRangeObservation(checker: checker, now: { clockReads += 1; return observedAt }, record: { recorded.append($0) })
            await observation.observe()?.value
            precondition(observation.assessment == result && recorded == [result])
            precondition(observation.adultConfirmedAt == (result == .adult ? observedAt : nil), "Expected adult completion time only for adult; received \(String(describing: observation.adultConfirmedAt)) for \(result)")
            precondition(clockReads == (result == .adult ? 1 : 0))
            await observation.observe()?.value
            precondition(checker.requests == 1, "View redraw must not repeat the system prompt")
        }
        let error = FakeAgeRangeChecker(.adult)
        error.failure = NSError(domain: "synthetic", code: 1)
        var failures: [DeclaredAgeAssessment] = []
        let failed = AgeRangeObservation(checker: error, record: { failures.append($0) })
        await failed.observe()?.value
        precondition(failed.assessment == .unavailable && failed.adultConfirmedAt == nil && failures == [.unavailable])

        let cancelled = FakeAgeRangeChecker(.adult)
        cancelled.failure = CancellationError()
        var cancelledResults: [DeclaredAgeAssessment] = []
        let interrupted = AgeRangeObservation(checker: cancelled, record: { cancelledResults.append($0) })
        await interrupted.observe()?.value
        precondition(interrupted.assessment == nil && interrupted.adultConfirmedAt == nil && cancelledResults.isEmpty)
        cancelled.failure = nil
        await interrupted.observe()?.value
        precondition(interrupted.assessment == .adult && cancelled.requests == 2 && cancelledResults == [.adult])

        let checker = PendingAgeRangeChecker()
        var recorded: [DeclaredAgeAssessment] = []
        let pending = AgeRangeObservation(checker: checker, record: { recorded.append($0) })
        let first = pending.observe()!
        await checker.waitForRequests(1)
        _ = pending.observe()
        precondition(checker.pending.count == 1 && pending.assessment == nil && pending.adultConfirmedAt == nil, "Pending request is deduplicated without an entry decision")
        pending.cancel()
        let second = pending.observe()!
        await checker.waitForRequests(2)
        checker.pending[1].resume(returning: .notShared)
        await second.value
        checker.pending[0].resume(returning: .adult)
        await first.value
        precondition(pending.assessment == .notShared && pending.adultConfirmedAt == nil && recorded == [.notShared], "Stale cancelled task must not overwrite or log the new observation")

        let delayedChecker = PendingAgeRangeChecker()
        var clock = Date(timeIntervalSince1970: 1767225600)
        let delayed = AgeRangeObservation(checker: delayedChecker, now: { clock }, record: { _ in })
        let completion = delayed.observe()!
        await delayedChecker.waitForRequests(1)
        precondition(delayed.adultConfirmedAt == nil)
        clock = Date(timeIntervalSince1970: 1767225660)
        delayedChecker.pending[0].resume(returning: .adult)
        await completion.value
        precondition(delayed.adultConfirmedAt == Date(timeIntervalSince1970: 1767225660), "Use completion time, not request or submit time")
        clock = Date(timeIntervalSince1970: 1767225720)
        await delayed.observe()?.value
        precondition(delayed.adultConfirmedAt == Date(timeIntervalSince1970: 1767225660), "Repeated reads retain the original observation instant")

        precondition(DeclaredAgeAssessment(lowerBound: nil, upperBound: 17) == .under18)
        precondition(DeclaredAgeAssessment(lowerBound: 18, upperBound: nil) == .adult)
        precondition(DeclaredAgeAssessment(lowerBound: nil, upperBound: nil) == .unknown)
        precondition(DeclaredAgeAssessment(lowerBound: 13, upperBound: 20) == .unknown)
        print("Age observation passed: 6 outcomes, error, cancellation and retry, pending deduplication, stale completion, adult completion time, 4 coarse ranges")
    }
}
