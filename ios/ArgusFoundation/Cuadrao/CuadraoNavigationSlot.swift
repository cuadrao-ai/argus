import CoreGraphics
import Foundation

enum CuadraoTab: Int, CaseIterable, Identifiable {
    case home, plan, assistant, search, profile
    var id: Self { self }
}

/// One slot of the navigation bar: a destination, or the add-movement action that takes the
/// assistant's place when the build has no assistant. The action is never a tab.
enum CuadraoNavigationSlot: Hashable, Identifiable {
    case tab(CuadraoTab)
    case add
    var id: Self { self }

    static func slots(hasAssistant: Bool) -> [CuadraoNavigationSlot] {
        CuadraoTab.allCases.map { tab in
            guard tab == .assistant else { return .tab(tab) }
            return hasAssistant ? .tab(tab) : .add
        }
    }
}

extension CuadraoNavigationSlot {
    /// Which slot a finger over the bar is on, for sliding across the bar. Slots share the width equally.
    static func index(forX x: CGFloat, width: CGFloat, count: Int) -> Int {
        guard count > 0, width > 0 else { return 0 }
        return min(count - 1, max(0, Int(x / (width / CGFloat(count)))))
    }
}

/// What the + menu can offer, in the order it is shown. Each row appears only when the thing behind it is real
/// in this build. The file rows form their own group below a divider.
enum CuadraoAddAction: String, CaseIterable, Identifiable {
    case account, transaction, plan, group, invite, scanCamera, choosePhoto, chooseFile
    var id: String { rawValue }

    var isFileAction: Bool { self == .scanCamera || self == .choosePhoto || self == .chooseFile }

    static func available(receiptsConnected: Bool, householdsAvailable: Bool, inHousehold: Bool) -> [CuadraoAddAction] {
        allCases.filter { action in
            switch action {
            case .account, .transaction, .plan: true
            case .scanCamera, .choosePhoto, .chooseFile: receiptsConnected
            case .group: householdsAvailable
            case .invite: householdsAvailable && inHousehold
            }
        }
    }
}
