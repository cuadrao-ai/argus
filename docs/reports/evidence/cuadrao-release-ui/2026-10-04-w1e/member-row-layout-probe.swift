// Host probe: swiftc -O -parse-as-library -o probe member-row-layout-probe.swift && ./probe
// old = cc68b341 row, c45e = c45e1eb7 row, fixed = trailing padding on a full-width button, overlay = the shipped row.
import SwiftUI
import AppKit

struct FrameKey: PreferenceKey {
    static var defaultValue: [String: CGRect] = [:]
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) { value.merge(nextValue()) { $1 } }
}
extension View {
    func mark(_ name: String) -> some View {
        background(GeometryReader { g in Color.clear.preference(key: FrameKey.self, value: [name: g.frame(in: .named("row"))]) })
    }
}
nonisolated(unsafe) var taps = 0
enum Variant: String, CaseIterable { case old, c45e, fixed, overlay }

struct Row: View {
    let variant: Variant; let name: String; let custom: Bool; let amount: String
    var label: some View {
        HStack { Image(systemName: "circle").mark("icon"); Circle().frame(width: 28, height: 28).mark("avatar"); Text(name).lineLimit(1).mark("name") }
    }
    @ViewBuilder var trailing: some View {
        if custom {
            VStack(alignment: .trailing) { Color.clear.frame(minWidth: 90, maxWidth: 140, minHeight: 44).mark("trailing") }
        } else { Text(amount).mark("trailing") }
    }
    var body: some View {
        HStack(spacing: 12) {
            switch variant {
            case .old:
                Button {} label: { label.frame(minHeight: 44) }.buttonStyle(.plain).mark("button")
                Spacer()
            case .overlay:
                Button {} label: { label.frame(minHeight: 44).contentShape(Rectangle()) }.buttonStyle(.plain).mark("button")
                Spacer().overlay { Color.clear.frame(height: 44).contentShape(Rectangle()).onTapGesture { taps += 1 }.mark("tap").padding(.trailing, 8).offset(x: -12).accessibilityHidden(true) }
            case .c45e:
                Button {} label: { label.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle()) }.buttonStyle(.plain).mark("button")
            case .fixed:
                Button {} label: { label.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle()) }.buttonStyle(.plain).mark("button").padding(.trailing, 20)
            }
            trailing
        }.coordinateSpace(name: "row")
    }
}

@MainActor func measure(_ v: Variant, _ name: String, _ custom: Bool, _ width: CGFloat) -> [String: CGRect] {
    var out: [String: CGRect] = [:]
    let host = NSHostingView(rootView: Row(variant: v, name: name, custom: custom, amount: "RD$1,234.56").frame(width: width).onPreferenceChange(FrameKey.self) { out = $0 })
    host.frame = CGRect(x: 0, y: 0, width: width, height: 60)
    let window = NSWindow(contentRect: host.frame, styleMask: [], backing: .buffered, defer: false)
    window.contentView = host
    host.layoutSubtreeIfNeeded()
    RunLoop.main.run(until: Date().addingTimeInterval(0.02))
    return out
}

@MainActor func click(_ name: String, _ custom: Bool, _ width: CGFloat, _ x: CGFloat) -> Int {
    taps = 0
    let host = NSHostingView(rootView: Row(variant: .overlay, name: name, custom: custom, amount: "RD$1,234.56").frame(width: width, height: 60))
    host.frame = CGRect(x: 0, y: 0, width: width, height: 60)
    let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
    window.contentView = host; window.orderFrontRegardless()
    host.layoutSubtreeIfNeeded(); RunLoop.main.run(until: Date().addingTimeInterval(0.05))
    for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
        let e = NSEvent.mouseEvent(with: type, location: CGPoint(x: x, y: 30), modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: 1)!
        window.sendEvent(e); RunLoop.main.run(until: Date().addingTimeInterval(0.05))
    }
    window.orderOut(nil)
    return taps
}

@MainActor func run() {
    // w=343, "Carolina", custom: button ends 109, spacer 121...191, field starts 203.
    for x in [100, 112, 118, 125, 150, 168, 174, 185, 197, 210] as [CGFloat] { print("click x=\(x) taps=\(click("Carolina", true, 343, x))") }
    let names = ["Ana", "Carolina", "María Fernanda", "María Fernanda de los Santos", "María Fernanda de los Santos Rodríguez y Pérez Guzmán"]
    var mismatches = 0, cases = 0, tapBad = 0; var by: [String: Int] = [:]
    for width in [280, 320, 343, 361, 398, 600] as [CGFloat] { for name in names { for custom in [false, true] {
        let old = measure(.old, name, custom, width)
        for v in [Variant.c45e, .fixed, .overlay] {
            let new = measure(v, name, custom, width)
            cases += 1
            let same = ["icon", "avatar", "name", "trailing"].allSatisfy { k in
                guard let a = old[k], let b = new[k] else { return false }
                return abs(a.minX - b.minX) < 0.01 && abs(a.width - b.width) < 0.01 && abs(a.minY - b.minY) < 0.01 && abs(a.height - b.height) < 0.01
            }
            if !same { mismatches += 1; by[v.rawValue, default: 0] += 1 }
            if v == .overlay, let t0 = new["tap"] { let t = t0; let ok = t.width < 0.01 || (abs(t.minX - new["button"]!.maxX) < 0.01 && abs(new["trailing"]!.minX - t.maxX - 32) < 0.01); if !ok { tapBad += 1; print("TAP w=\(Int(width)) custom=\(custom) name=\(name.count) tap=\(t) button=\(new["button"]!) trailing=\(new["trailing"]!)") } }
            if v == .overlay && name.count == 8 && width == 343 { print("overlay tap area w=343 custom=\(custom): \(new["tap"]!) button maxX=\(new["button"]!.maxX) trailing minX=\(new["trailing"]!.minX)") }
            if !same && v == .fixed {
                let gapOld = old["trailing"]!.minX - old["name"]!.maxX, gapNew = new["trailing"]!.minX - new["name"]!.maxX
                let dead = new["trailing"]!.minX - new["button"]!.maxX
                print("\(same ? "same" : "DIFF") \(v.rawValue) w=\(Int(width)) custom=\(custom) name=\(name.count)ch  name old x=\(old["name"]!.minX) w=\(old["name"]!.width) new w=\(new["name"]!.width)  trailing old x=\(old["trailing"]!.minX) w=\(old["trailing"]!.width) new x=\(new["trailing"]!.minX) w=\(new["trailing"]!.width)  gap old=\(gapOld) new=\(gapNew) untappable-before-trailing=\(dead)")
            }
        }
    } } }
    print("cases=\(cases) mismatches=\(mismatches) by variant=\(by) tapBad=\(tapBad)")
}
@main struct Main { @MainActor static func main() { _ = NSApplication.shared; run() } }
