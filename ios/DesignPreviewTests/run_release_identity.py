"""Run pure identity-state checks without a simulator, account service or provider."""
from pathlib import Path
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
identity = root / "ios/ArgusFoundation/ReleaseUI/Identity"
with tempfile.TemporaryDirectory(prefix="cuadrao-identity-checks-") as folder:
    helper = prepare(root, Path(folder))
    executable = str(Path(folder) / "checks")
    subprocess.run([
        "xcrun", "swiftc", str(helper), "-module-cache-path", str(Path(folder) / "ModuleCache"),
        str(identity / "ReleaseIdentityModels.swift"),
        str(Path(__file__).with_name("ReleaseIdentityChecks.swift")), "-o", executable,
    ], check=True)
    subprocess.run([executable], check=True)
