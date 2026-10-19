import Combine
import Foundation
import OSLog

@MainActor
final class AgeRangeObservation: ObservableObject {
    static let shared = AgeRangeObservation(checker: AppleAgeRangeChecker())
    private(set) var assessment: DeclaredAgeAssessment?
    private let checker: any AgeRangeChecking
    private let record: (DeclaredAgeAssessment) -> Void
    private var requestID: UUID?
    private var task: Task<Void, Never>?

    init(checker: any AgeRangeChecking, record: ((DeclaredAgeAssessment) -> Void)? = nil) {
        self.checker = checker
        self.record = record ?? { assessment in
            Logger(subsystem: "local.cuadrao.age-range", category: "observation")
                .notice("result=\(assessment.rawValue, privacy: .public)")
        }
    }

    @discardableResult
    func observe() -> Task<Void, Never>? {
        guard assessment == nil, task == nil else { return task }
        let id = UUID()
        requestID = id
        let checker = checker
        let task = Task { [weak self] in
            defer {
                if self?.requestID == id {
                    self?.requestID = nil
                    self?.task = nil
                }
            }
            let result: DeclaredAgeAssessment
            do { result = try await checker.request() }
            catch is CancellationError { return }
            catch { result = .unavailable }
            guard !Task.isCancelled, let self, self.requestID == id else { return }
            self.assessment = result
            self.record(result)
        }
        self.task = task
        return task
    }

    func cancel() {
        requestID = nil
        task?.cancel()
        task = nil
    }

    deinit { task?.cancel() }
}
