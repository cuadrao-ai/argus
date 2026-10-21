"""Run every DesignPreviewTests check with a Linux Swift toolchain (no Xcode, no simulator).

The checks exercise preview state only. On Linux there is no SwiftUI or CoreGraphics, so this
runner copies the sources into a temporary folder, swaps those imports for Foundation and
Observation, and adds one stand-in for SwiftUI's `move(fromOffsets:toOffset:)`. It does not replace the Mac runners
(`run_*.py`), which compile the unmodified sources with `xcrun swiftc`.

Usage: python3 ios/DesignPreviewTests/run_linux.py [--swiftc PATH]
"""
from pathlib import Path
import argparse
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
canvas = root / "ios/ArgusFoundation/Cuadrao"
here = Path(__file__).parent
SHIM = '''import Foundation
extension Array {
    mutating func move(fromOffsets source: IndexSet, toOffset destination: Int) {
        let moving = source.map { self[$0] }
        let before = source.filter { $0 < destination }.count
        for index in source.sorted(by: >) { remove(at: index) }
        insert(contentsOf: moving, at: destination - before)
    }
}
'''


def linux(text: str) -> str:
    return text.replace("import SwiftUI", "import Foundation\nimport Observation").replace("import CoreGraphics", "")


def copy(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(linux(text))
    return path


def source(name: str) -> str:
    return (canvas / name).read_text()


def run(swiftc: str, folder: Path, label: str, files: list) -> None:
    binary = folder / label
    subprocess.run([swiftc, str(prepare(root, folder)), *map(str, files), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--swiftc", default="swiftc")
    swiftc = parser.parse_args().swiftc
    with tempfile.TemporaryDirectory(prefix="cuadrao-linux-checks-") as temporary:
        folder = Path(temporary)
        shim = copy(folder, "Shim.swift", SHIM)
        flag = canvas / "CuadraoDesignPreview.swift"
        accounts = copy(folder, "Accounts.swift", source("CuadraoAccountsPreview.swift").split("struct CanvasAccountIcon:")[0])
        household = copy(folder, "Household.swift", "enum CanvasHouseholdState { case alone, joined(String) }")
        spaces = copy(folder, "Spaces.swift", source("CuadraoSpacesPreview.swift"))
        history = [canvas / n for n in ["CuadraoCollectionOrder.swift", "CuadraoSpendingHistory.swift",
                                        "CuadraoSpendingStory.swift", "CuadraoBalanceHistory.swift", "CuadraoBalancePeriod.swift"]]
        plan = [canvas / "CuadraoCollectionOrder.swift", canvas / "CanvasMoney.swift", canvas / "Planning/PlanScenario.swift", canvas / "Planning/CuadraoPlanPreview.swift", flag]
        run(swiftc, folder, "plan", plan + [here / "PlanPreviewChecks.swift"])
        run(swiftc, folder, "group", plan + [canvas / "Planning/CuadraoGroupPreview.swift",
                                             canvas / "Receipts/CuadraoReceipt.swift", here / "GroupPreviewChecks.swift"])
        run(swiftc, folder, "home", [shim, accounts, household, spaces, *history, here / "HomeBalanceChecks.swift"])
        run(swiftc, folder, "receipt", [shim, accounts, household, spaces, *history, canvas / "CanvasMoney.swift",
                                        canvas / "Planning/PlanScenario.swift", canvas / "Planning/CuadraoPlanPreview.swift", canvas / "Planning/CuadraoGroupPreview.swift",
                                        canvas / "Receipts/CuadraoReceipt.swift", canvas / "Receipts/CuadraoReceiptStore.swift",
                                        flag, here / "ReceiptPreviewChecks.swift"])
        run(swiftc, folder, "avatar", [copy(folder, "Geometry.swift", source("CuadraoAvatarCropGeometry.swift")),
                                       copy(folder, "AvatarCropChecks.swift", (here / "AvatarCropChecks.swift").read_text())])
        chat = [copy(folder, "References.swift", source("CuadraoSearchReferences.swift").split("struct CuadraoSearchReferenceDetail: View {")[0]),
                copy(folder, "Context.swift", source("CuadraoChatContext.swift").split("private struct CuadraoChatKey: EnvironmentKey {")[0])]
        chat += [copy(folder, n, source(n)) for n in ["CuadraoChatPreview.swift", "CuadraoVoicePreview.swift", "CuadraoVoiceMessagePreview.swift"]]
        run(swiftc, folder, "chat", [shim, *chat, here / "TemporaryChatChecks.swift"])


if __name__ == "__main__":
    main()
