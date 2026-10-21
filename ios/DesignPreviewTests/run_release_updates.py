"""Run pure display-contract checks without a simulator or notification provider."""
from pathlib import Path
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
updates = root / "ios/ArgusFoundation/ReleaseUI/Updates"
with tempfile.TemporaryDirectory(prefix="cuadrao-updates-checks-") as folder:
    helper = prepare(root, Path(folder))
    executable = str(Path(folder) / "checks")
    subprocess.run([
        "xcrun", "swiftc", str(helper), "-module-cache-path", str(Path(folder) / "ModuleCache"),
        str(updates / "ReleaseUpdateModels.swift"),
        str(updates / "ReleaseUpdateCopy.swift"),
        str(root / "ios/ArgusFoundation/Cuadrao/CanvasMoney.swift"),
        str(Path(__file__).with_name("ReleaseUpdatesChecks.swift")), "-o", executable,
    ], check=True)
    subprocess.run([executable], check=True)
