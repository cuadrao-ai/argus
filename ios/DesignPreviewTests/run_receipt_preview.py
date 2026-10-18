from pathlib import Path
import subprocess
import sys
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
canvas = root / "ios/ArgusFoundation/Cuadrao"
tests = Path(__file__).resolve().parent
checks = (tests / (sys.argv[1] if len(sys.argv) > 1 else "ReceiptPreviewChecks.swift")).resolve()
if len(sys.argv) > 2 or checks.parent != tests or checks.suffix != ".swift" or not checks.is_file():
    raise SystemExit("Choose one Swift checks file in ios/DesignPreviewTests.")
with tempfile.TemporaryDirectory(prefix="cuadrao-receipt-checks-") as temporary:
    helper = prepare(root, Path(temporary))
    folder = Path(temporary)
    source = (canvas / "CuadraoAccountsPreview.swift").read_text().split("struct CanvasAccountIcon:")[0]
    (folder / "Accounts.swift").write_text(source)
    (folder / "Household.swift").write_text("enum CanvasHouseholdState { case alone, joined(String) }")
    book = root / "ios/Packages/CuadraoBook/Sources/CuadraoBook"
    subprocess.run(["xcrun", "swiftc", "-parse-as-library", "-emit-library", "-static", "-emit-module",
                    "-module-name", "CuadraoBook", "-module-cache-path", str(folder / "modules"),
                    "-emit-module-path", str(folder / "CuadraoBook.swiftmodule"),
                    *map(str, sorted(book.glob("*.swift"))), "-o", str(folder / "libCuadraoBook.a")], check=True)
    files = [folder / "Accounts.swift", folder / "Household.swift"]
    files += [canvas / name for name in [
        "CanvasMoney.swift", "CuadraoSpacesPreview.swift", "CuadraoCollectionOrder.swift",
        "CuadraoSpendingHistory.swift", "CuadraoSpendingStory.swift", "CuadraoBalanceHistory.swift", "CuadraoBalancePeriod.swift",
        "Planning/CuadraoPlanPreview.swift", "Planning/PlanScenario.swift", "Planning/CuadraoGroupPreview.swift",
        "Receipts/CuadraoReceipt.swift", "Receipts/CuadraoReceiptStore.swift", "CuadraoDesignPreview.swift",
    ]]
    files.append(checks)
    subprocess.run(["xcrun", "swiftc", str(helper), "-module-cache-path", str(folder / "modules"),
                    "-I", str(folder), "-L", str(folder), "-lCuadraoBook",
                    *map(str, files), "-o", str(folder / "checks")], check=True)
    subprocess.run([str(folder / "checks")], check=True)
