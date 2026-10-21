"""Run the native preview's actual chat model, using the existing build cache."""
from pathlib import Path
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
canvas = root / "ios/ArgusFoundation/Cuadrao"
with tempfile.TemporaryDirectory(prefix="cuadrao-chat-checks-") as folder:
    helper = prepare(root, Path(folder))
    work = Path(folder)
    # Use the exact fixture declarations; the view below them is irrelevant to state checks.
    fixtures = (canvas / "CuadraoSearchReferences.swift").read_text().split("struct CuadraoSearchReferenceDetail: View {")[0]
    (work / "References.swift").write_text(fixtures)
    context = (canvas / "CuadraoChatContext.swift").read_text().split("private struct CuadraoChatKey: EnvironmentKey {")[0]
    (work / "Context.swift").write_text(context)
    binary = work / "checks"
    subprocess.run([
        "xcrun", "swiftc", str(helper), "-module-cache-path", "/private/tmp/cuadrao-native-design-build/ModuleCache.noindex",
        str(canvas / "CuadraoChatPreview.swift"), str(canvas / "CuadraoVoicePreview.swift"), str(canvas / "CuadraoVoiceMessagePreview.swift"), str(work / "References.swift"), str(work / "Context.swift"),
        str(Path(__file__).with_name("TemporaryChatChecks.swift")), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
