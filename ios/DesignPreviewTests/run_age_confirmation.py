"""Exercise the production age policy and store with synthetic Apple results, without providers."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
paths = [
    "ios/Packages/ArgusSession/Sources/ArgusSession/AgeConfirmation.swift",
    "ios/ArgusFoundation/Auth/AgeConfirmationPolicy.swift",
    "ios/ArgusFoundation/Auth/AgeConfirmationModel.swift",
    "ios/ArgusFoundation/Cuadrao/CuadraoLegalURLs.swift",
    "ios/DesignPreviewTests/AgeConfirmationChecks.swift",
]
with tempfile.TemporaryDirectory(prefix="cuadrao-age-confirmation-") as directory:
    directory = Path(directory)
    sources = []
    for index, path in enumerate(paths):
        source = directory / f"Age{index}.swift"
        source.write_text((root / path).read_text().replace("import ArgusSession\n", ""))
        sources.append(str(source))
    executable = directory / "checks"
    subprocess.run(["xcrun", "swiftc", "-module-cache-path", str(directory / "ModuleCache"),
                    *sources, "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
