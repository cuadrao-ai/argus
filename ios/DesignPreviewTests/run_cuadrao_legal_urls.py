"""The legal page URLs have one owner, start empty in both builds, and no screen builds a legal link from the web origin."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
app = root / "ios/ArgusFoundation"
owner = (app / "Cuadrao/CuadraoLegalURLs.swift").read_text()

stray = [str(path.relative_to(root)) for path in app.rglob("*.swift")
         if re.search(r'appendingPathComponent\("(terms|privacy)"\)', path.read_text())]
assert not stray, "legal links must come from CuadraoLegalURLs, not the web origin: " + ", ".join(stray)
recovery = (app / "Auth/NativeAuthConfiguration.swift").read_text()
assert 'webURL.appendingPathComponent("auth/forgot-password")' in recovery, "password recovery keeps the web origin"

checks = r'''
let test = "--cuadrao-legal-test-urls"
let empty = CuadraoLegalURLs.current(arguments: [])
precondition(empty == CuadraoLegalURLs.published, "no argument, no URLs")
precondition(empty.privacy == nil && empty.terms == nil && empty.dataDeletion == nil, "published is empty")
precondition(!empty.hasPages, "an empty owner reports no pages")
precondition(!empty.hasTermsAndPrivacy, "an empty owner does not support the acceptance sentence")
let overridden = CuadraoLegalURLs.current(arguments: ["app", test])
#if DEBUG
precondition(overridden.privacy?.absoluteString == "https://legal.example.test/privacidad")
precondition(overridden.terms?.absoluteString == "https://legal.example.test/terminos")
precondition(overridden.dataDeletion?.absoluteString == "https://legal.example.test/eliminar-datos")
precondition(overridden.hasPages)
precondition(overridden.hasTermsAndPrivacy, "both documents set supports the acceptance sentence")
#else
precondition(overridden == empty, "a Release build ignores the test argument")
#endif
for (argument, termsExpected) in [("--cuadrao-legal-test-terms-only", true), ("--cuadrao-legal-test-privacy-only", false)] {
    let single = CuadraoLegalURLs.current(arguments: [argument])
    #if DEBUG
    precondition(single.hasPages && !single.hasTermsAndPrivacy)
    precondition((single.terms != nil) == termsExpected)
    precondition((single.privacy != nil) != termsExpected)
    #else
    precondition(single == empty, "Release ignores single-page fixtures")
    #endif
}
let termsOnly = CuadraoLegalURLs(terms: URL(string: "https://legal.example.test/t"))
let privacyOnly = CuadraoLegalURLs(privacy: URL(string: "https://legal.example.test/p"))
precondition(termsOnly.hasPages && privacyOnly.hasPages, "one page is enough for a link group")
precondition(!termsOnly.hasTermsAndPrivacy && !privacyOnly.hasTermsAndPrivacy, "one document alone keeps the sentence hidden")
precondition(CuadraoLegalURLs(privacy: privacyOnly.privacy, terms: termsOnly.terms).hasTermsAndPrivacy, "both documents set")
print("Legal URL owner passed")
'''
with tempfile.TemporaryDirectory(prefix="cuadrao-legal-urls-") as folder:
    folder = Path(folder)
    swift = folder / "main.swift"
    swift.write_text(owner + checks)
    for mode in ["Debug", "Release"]:
        executable = folder / mode
        command = ["xcrun", "swiftc", "-module-cache-path", str(folder / "ModuleCache")]
        if mode == "Debug":
            command += ["-D", "DEBUG"]
        subprocess.run(command + [str(swift), "-o", str(executable)], check=True)
        print(mode, flush=True)
        subprocess.run([str(executable)], check=True)
