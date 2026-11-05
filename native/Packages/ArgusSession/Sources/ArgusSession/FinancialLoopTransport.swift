import Foundation

extension SessionController {
    public func financialActivityOptions(expectedIdentity: SessionSnapshot) async throws -> FinancialActivityOptions {
        try await loopResponse(route: "financial-activities", path: "/options", identity: expectedIdentity)
    }

    public func financialPurchases(currency: String, expectedIdentity: SessionSnapshot) async throws -> FinancialPurchaseCatalog {
        try await loopResponse(route: "financial-activities", path: "/purchases",
                               query: [URLQueryItem(name: "currency", value: currency)], identity: expectedIdentity)
    }

    public func financialActivityPreview(_ command: FinancialActivityCommand, activityId: UUID? = nil,
                                         expectedIdentity: SessionSnapshot) async throws -> FinancialActivityPreview {
        let path = activityId.map { "/" + $0.uuidString } ?? ""
        return try await loopResponse(route: "financial-activities", path: path + "/preview", method: "POST",
                                      body: encoded(command), identity: expectedIdentity)
    }

    public func financialActivityDetail(_ activityId: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialActivityDetail {
        try await loopResponse(route: "financial-activities", path: "/" + activityId.uuidString,
                               identity: expectedIdentity)
    }

    public func financialActivityDetailHistory(_ activityId: UUID, expectedIdentity: SessionSnapshot) async throws -> FinancialPage<FinancialActivityDetail> {
        try await loopResponse(route: "financial-activities", path: "/" + activityId.uuidString + "/history",
                               identity: expectedIdentity)
    }

    /// The journaled body is the exact confirmed command. The session transport
    /// still checks the current owner and epoch before and after the request.
    public func sendFinancialConfirmation(_ write: PendingFinancialConfirmation,
                                          expectedIdentity: SessionSnapshot) async throws -> FinancialActivityReceipt {
        guard expectedIdentity.profile.flatMap({ UUID(uuidString: $0.id) }) == write.ownerId,
              write.route == "financial-activities",
              write.path == "" || write.path == "/" || UUID(uuidString: String(write.path.dropFirst())) != nil,
              write.method == "POST" || write.method == "PATCH"
        else { throw SessionFailure.invalidResponse }
        return try await loopResponse(route: write.route, path: write.path == "/" ? "" : write.path,
                                      method: write.method, body: write.body, key: write.key,
                                      identity: expectedIdentity)
    }

    public func openingPreview(accountId: UUID, request: WriteOpeningRequest, expectedIdentity: SessionSnapshot) async throws -> OpeningPreview {
        try await loopResponse(path: accountPath(accountId) + "/opening/preview", method: "POST", body: encoded(request), identity: expectedIdentity)
    }
    public func financialCategories(expectedIdentity: SessionSnapshot) async throws -> FinancialCategoryCatalog {
        try await loopResponse(route: "financial-categories", identity: expectedIdentity)
    }

    public func financialHome(month: String? = nil, timeZone: String = "America/Santo_Domingo",
                              expectedIdentity: SessionSnapshot) async throws -> FinancialHome {
        var query = [URLQueryItem(name: "time_zone", value: timeZone)]
        if let month { query.append(URLQueryItem(name: "month", value: month)) }
        return try await loopResponse(route: "financial-home", query: query, identity: expectedIdentity)
    }

    public func financialActivity(accountId: UUID, cursor: String? = nil, expectedIdentity: SessionSnapshot) async throws -> FinancialPage<FinancialActivity> {
        try await loopResponse(path: accountPath(accountId) + "/activity", query: pageQuery(cursor), identity: expectedIdentity)
    }

    public func financialActivityHistory(accountId: UUID, recordId: UUID, cursor: String? = nil, expectedIdentity: SessionSnapshot) async throws -> FinancialPage<FinancialActivity> {
        try await loopResponse(path: activityPath(accountId, recordId) + "/history", query: pageQuery(cursor), identity: expectedIdentity)
    }

    public func financialChecks(accountId: UUID, cursor: String? = nil, expectedIdentity: SessionSnapshot) async throws -> FinancialPage<FinancialCheck> {
        try await loopResponse(path: accountPath(accountId) + "/balance-checks", query: pageQuery(cursor), identity: expectedIdentity)
    }

    public func expensePreview(accountId: UUID, recordId: UUID? = nil, request: ExpenseRequest,
                               expectedIdentity: SessionSnapshot) async throws -> ExpensePreview {
        try await loopResponse(path: activityPath(accountId, recordId) + "/preview", method: "POST",
                               body: encoded(request), identity: expectedIdentity)
    }

    public func saveExpense(accountId: UUID, recordId: UUID? = nil, request: ExpenseRequest, key: UUID,
                            expectedIdentity: SessionSnapshot) async throws -> ExpenseReceipt {
        try await loopResponse(path: activityPath(accountId, recordId), method: recordId == nil ? "POST" : "PATCH",
                               body: encoded(request), key: key, identity: expectedIdentity)
    }

    public func balanceCheckPreview(accountId: UUID, request: BalanceCheckRequest,
                                    expectedIdentity: SessionSnapshot) async throws -> BalanceCheckPreview {
        try await loopResponse(path: accountPath(accountId) + "/balance-checks/preview", method: "POST",
                               body: encoded(request), identity: expectedIdentity)
    }

    public func saveBalanceCheck(accountId: UUID, request: BalanceCheckRequest, key: UUID,
                                 expectedIdentity: SessionSnapshot) async throws -> BalanceCheckReceipt {
        try await loopResponse(path: accountPath(accountId) + "/balance-checks", method: "POST",
                               body: encoded(request), key: key, identity: expectedIdentity)
    }

    private func accountPath(_ accountId: UUID) -> String { "/" + accountId.uuidString }
    private func activityPath(_ accountId: UUID, _ recordId: UUID?) -> String {
        accountPath(accountId) + "/activity" + (recordId.map { "/" + $0.uuidString } ?? "")
    }
    private func pageQuery(_ cursor: String?) -> [URLQueryItem] {
        cursor.map { [URLQueryItem(name: "cursor", value: $0)] } ?? []
    }
    private func loopResponse<Value: Decodable>(route: String = "financial-accounts", path: String = "",
                                               method: String = "GET", body: Data? = nil, key: UUID? = nil,
                                               query: [URLQueryItem] = [], identity: SessionSnapshot) async throws -> Value {
        let data = try await financialRequest(route: route, path: path, method: method, body: body,
                                              key: key?.uuidString, query: query, expectedIdentity: identity)
        do { return try JSONDecoder().decode(Value.self, from: data) }
        catch { throw SessionFailure.invalidResponse }
    }
}
