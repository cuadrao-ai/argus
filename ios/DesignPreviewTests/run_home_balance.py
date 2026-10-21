"""Exercise the preview's actual account types and recorded-balance projection."""
from pathlib import Path
import subprocess
import tempfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
canvas = root / "ios/ArgusFoundation/Cuadrao"
with tempfile.TemporaryDirectory(prefix="cuadrao-home-checks-") as folder:
    helper = prepare(root, Path(folder))
    folder = Path(folder)
    source = (canvas / "CuadraoAccountsPreview.swift").read_text().split("struct CanvasAccountIcon:")[0]
    (folder / "Accounts.swift").write_text(source)
    (folder / "Household.swift").write_text('enum CanvasHouseholdState { case alone, joined(String) }')
    subprocess.run(["xcrun", "swiftc", str(helper), "-module-cache-path", "/private/tmp/cuadrao-native-design-build/ModuleCache.noindex",
        str(folder / "Accounts.swift"), str(folder / "Household.swift"), str(canvas / "CuadraoSpacesPreview.swift"),
        str(canvas / "CuadraoCollectionOrder.swift"), str(canvas / "CuadraoSpendingHistory.swift"), str(canvas / "CuadraoSpendingStory.swift"), str(canvas / "CuadraoBalanceHistory.swift"), str(canvas / "CuadraoBalancePeriod.swift"), str(Path(__file__).with_name("HomeBalanceChecks.swift")), "-o", str(folder / "checks")], check=True)
    subprocess.run([str(folder / "checks")], check=True)
