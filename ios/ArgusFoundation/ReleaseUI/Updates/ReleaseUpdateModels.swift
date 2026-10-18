import Foundation

struct ReleaseUpdateItem: Identifiable {
    let id: String
    let kind: ReleaseUpdateKind
    let occurredAt: Date
    var isRead: Bool
    let source: ReleaseUpdateSource
}

enum ReleaseUpdateSource {
    case available(ReleaseUpdateDestination)
    case unavailable
}

enum ReleaseUpdateDestination: Equatable {
    case bill(String), document(String), household(String), plan(String), account(String)
}

enum ReleaseBillReminder: Int, CaseIterable {
    case threeDaysBefore = 3, dueToday = 0

    static func matching(dueDate: Date, on date: Date, calendar: Calendar) -> Self? {
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: date),
                                           to: calendar.startOfDay(for: dueDate)).day
        return days.flatMap(Self.init(rawValue:))
    }
}

struct ReleaseClosedBalance {
    let amount: Decimal
    let currency: String
    init?(amount: Decimal, currency: String) {
        guard amount != 0 else { return nil }
        self.amount = amount
        self.currency = currency
    }
}

enum ReleaseUpdateKind {
    case bill(name: String, reminder: ReleaseBillReminder)
    case draftReady
    case invitationAccepted(member: String)
    case householdAdminHandoff
    case householdClosed
    case movedAccountHistory(account: String)
    case ownerHistoryRemoved
    case formerMember(plan: String, closedBalance: ReleaseClosedBalance?)
    case reassignResponsibilities(plan: String)
    case newPlanOwner(plan: String)
}

enum ReleaseUpdatesState {
    case unavailable, loading, empty, failure
    case loaded([ReleaseUpdateItem], more: ReleaseUpdatesMore = .none)
}

enum ReleaseUpdatesMore { case none, available, loading, failure }
enum ReleasePushPermission: String, CaseIterable {
    case unavailable, notDetermined, requesting, authorized, denied
}

enum ReleaseSafePushCopy {
    static func title(spanish: Bool) -> String { CuadraoCopy.text("copy.releaseUpdateModels.bb8491d942", spanish: spanish) }
    static func body(spanish: Bool) -> String {
        CuadraoCopy.text("copy.releaseUpdateModels.5bfaa448c2", spanish: spanish)
    }
}

enum ReleaseRecordedMonth: Equatable {
    case missingCoverage
    case recorded(Decimal)
    enum Comparison: Equatable { case unavailable, amount(Decimal), percentage(Decimal) }
    func compared(to previous: Self) -> Comparison {
        guard case let .recorded(current) = self, case let .recorded(prior) = previous else { return .unavailable }
        let difference = current - prior
        return prior == 0 ? .amount(difference) : .percentage(difference / abs(prior) * 100)
    }
}

enum ReleaseHistoryAccess {
    case editable, readOnly
    case movedOutOfHousehold
}
