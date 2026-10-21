"""Verify the actual UI-only Plan state without a simulator, service, or model call."""
from pathlib import Path
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="cuadrao-plan-checks-") as folder:
    helper = prepare(root, Path(folder))
    binary = Path(folder) / "checks"
    subprocess.run([
        "xcrun", "swiftc", str(helper), "-module-cache-path", "/private/tmp/cuadrao-native-design-build/ModuleCache.noindex",
        str(root / "ios/ArgusFoundation/Cuadrao/CuadraoCollectionOrder.swift"),
        str(root / "ios/ArgusFoundation/Cuadrao/CanvasMoney.swift"),
        str(root / "ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanPreview.swift"),
        str(root / "ios/ArgusFoundation/Cuadrao/Planning/PlanScenario.swift"),
        str(root / "ios/ArgusFoundation/Cuadrao/CuadraoDesignPreview.swift"),
        str(Path(__file__).with_name("PlanPreviewChecks.swift")), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
