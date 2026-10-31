import Foundation

extension SessionController {
    public func financialPlan(endDate: String? = nil, expectedIdentity: SessionSnapshot) async throws -> FinancialPlanProjection {
        let query = endDate.map { [URLQueryItem(name: "end_date", value: $0)] } ?? []
        return try await planResponse(query: query, identity: expectedIdentity)
    }

    public func financialPlanCandidates(occurrenceId: String, expectedIdentity: SessionSnapshot) async throws -> FinancialPurchaseCatalog {
        try await planResponse(path: "/occurrences/" + occurrenceId + "/candidates", identity: expectedIdentity)
    }

    public func financialPlanPreview(occurrenceId: String, command: FinancialPlanFulfillmentCommand,
                                     expectedIdentity: SessionSnapshot) async throws -> FinancialPlanFulfillmentPreview {
        try await planResponse(path: "/occurrences/" + occurrenceId + "/fulfillment/preview",
                               method: "POST", body: encoded(command), identity: expectedIdentity)
    }

    public func sendPlanConfirmation(_ write: PendingFinancialConfirmation, expectedIdentity: SessionSnapshot) async throws {
        let operation = try validatedPlanOperation(write, identity: expectedIdentity)
        switch operation {
        case .createDebt, .editDebt, .linkDebt:
            let _: FinancialDebtReceipt = try await planResponse(path: operation.path, method: operation.method, body: write.body, key: write.key, identity: expectedIdentity)
        case .createGoal, .editGoal, .linkGoal, .releaseGoal:
            let _: FinancialGoalReceipt = try await planResponse(path: operation.path, method: operation.method, body: write.body, key: write.key, identity: expectedIdentity)
        case .allocateGoals:
            let _: FinancialGoalAllocationReceipt = try await planResponse(path: operation.path, method: operation.method, body: write.body, key: write.key, identity: expectedIdentity)
        case .createBudget, .editBudget:
            let _: FinancialBudgetReceipt = try await planResponse(path: operation.path, method: operation.method,
                body: write.body, key: write.key, identity: expectedIdentity)
        case .createExpectation, .editExpectation:
            let _: FinancialExpectationReceipt = try await planResponse(path: operation.path, method: operation.method,
                body: write.body, key: write.key, identity: expectedIdentity)
        case .selection:
            let _: FinancialPlanSelectionReceipt = try await planResponse(path: operation.path, method: operation.method,
                body: write.body, key: write.key, identity: expectedIdentity)
        case .link:
            let _: FinancialPlanLinkReceipt = try await planResponse(path: operation.path, method: operation.method,
                body: write.body, key: write.key, identity: expectedIdentity)
        case .fulfill, .recordGoal, .recordDebt: throw SessionFailure.invalidResponse
        }
    }

    public func sendPlanFulfillment(_ write: PendingFinancialConfirmation, expectedIdentity: SessionSnapshot) async throws -> FinancialActivityReceipt {
        let operation = try validatedPlanOperation(write, identity: expectedIdentity)
        guard operation.recordsActivity else { throw SessionFailure.invalidResponse }
        return try await planResponse(path: operation.path, method: operation.method, body: write.body,
                                       key: write.key, identity: expectedIdentity)
    }

    private func validatedPlanOperation(_ write: PendingFinancialConfirmation, identity: SessionSnapshot) throws -> FinancialPlanOperation {
        guard identity.profile.flatMap({ UUID(uuidString: $0.id) }) == write.ownerId,
              let operation = write.planOperation, write.route == "financial-plan",
              write.path == operation.path, write.method == operation.method else { throw SessionFailure.invalidResponse }
        return operation
    }

    func planResponse<Value: Decodable>(path: String = "", method: String = "GET", body: Data? = nil,
        key: UUID? = nil, query: [URLQueryItem] = [], identity: SessionSnapshot) async throws -> Value {
        let data = try await financialRequest(route: "financial-plan", path: path, method: method, body: body,
                                              key: key?.uuidString, query: query, expectedIdentity: identity)
        do { return try JSONDecoder().decode(Value.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }
}
