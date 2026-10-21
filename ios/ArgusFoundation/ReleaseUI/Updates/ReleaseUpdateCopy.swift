import Foundation

extension ReleaseUpdateKind {
    func title(spanish es: Bool) -> String {
        switch self {
        case .bill(_, let reminder):
            (reminder == .dueToday ? CuadraoCopy.text("copy.releaseUpdateCopy.94166365d1", spanish: es) : CuadraoCopy.text("copy.releaseUpdateCopy.aefe9eba3e", spanish: es))
        case .draftReady: CuadraoCopy.text("copy.releaseUpdateCopy.6e96f38496", spanish: es)
        case .invitationAccepted: CuadraoCopy.text("copy.releaseUpdateCopy.0916da1575", spanish: es)
        case .householdAdminHandoff: CuadraoCopy.text("copy.releaseUpdateCopy.bc91cb59ba", spanish: es)
        case .householdClosed: CuadraoCopy.text("copy.releaseUpdateCopy.76fc389451", spanish: es)
        case .movedAccountHistory: CuadraoCopy.text("copy.releaseUpdateCopy.1765826ace", spanish: es)
        case .ownerHistoryRemoved: CuadraoCopy.text("copy.releaseUpdateCopy.26d27e2607", spanish: es)
        case .formerMember: CuadraoCopy.text("copy.releaseUpdateCopy.179dc56123", spanish: es)
        case .reassignResponsibilities: CuadraoCopy.text("copy.releaseUpdateCopy.817adee716", spanish: es)
        case .newPlanOwner: CuadraoCopy.text("copy.releaseUpdateCopy.566f6ce34d", spanish: es)
        }
    }

    func detail(spanish es: Bool) -> String {
        switch self {
        case .bill(let name, _): return name
        case .draftReady:
            return CuadraoCopy.text("copy.releaseUpdateCopy.acc1ea1c32", spanish: es)
        case .invitationAccepted(let member):
            return CuadraoCopy.text("copy.releaseUpdateCopy.20aa0e4e4b", spanish: es, String(describing: member))
        case .householdAdminHandoff:
            return CuadraoCopy.text("copy.releaseUpdateCopy.c3c8459810", spanish: es)
        case .householdClosed:
            return CuadraoCopy.text("copy.releaseUpdateCopy.85e04719dd", spanish: es)
        case .movedAccountHistory(let account):
            return CuadraoCopy.text("copy.releaseUpdateCopy.3de773cc89", spanish: es, String(describing: account))
        case .ownerHistoryRemoved:
            return CuadraoCopy.text("copy.releaseUpdateCopy.422340e7e8", spanish: es)
        case .formerMember(let plan, let balance):
            let base = CuadraoCopy.text("copy.releaseUpdateCopy.1a0d36e8f5", spanish: es, String(describing: plan))
            guard let balance else { return base }
            let amount = balance.currency + " " + CanvasMoney.format(balance.amount, currency: balance.currency)
            return base + (CuadraoCopy.text("copy.releaseUpdateCopy.bc1309c763", spanish: es, String(describing: amount)))
        case .reassignResponsibilities(let plan):
            return CuadraoCopy.text("copy.releaseUpdateCopy.37c24a4c36", spanish: es, String(describing: plan))
        case .newPlanOwner(let plan):
            return CuadraoCopy.text("copy.releaseUpdateCopy.aef8ec8d49", spanish: es, String(describing: plan))
        }
    }

    var symbol: String {
        switch self {
        case .bill: "calendar"
        case .draftReady: "doc.text"
        case .invitationAccepted, .householdAdminHandoff: "person.2"
        case .householdClosed: "house"
        case .movedAccountHistory: "clock.arrow.circlepath"
        case .ownerHistoryRemoved: "clock.badge.xmark"
        case .formerMember: "person.crop.circle.badge.minus"
        case .reassignResponsibilities, .newPlanOwner: "list.bullet.rectangle"
        }
    }
}
