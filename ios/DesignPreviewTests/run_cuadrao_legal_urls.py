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
let configuredValues: [String: Any] = [
    "ARGUS_CUADRAO_TERMS_URL": "https://cuadrao.ai/terminos",
    "ARGUS_CUADRAO_PRIVACY_URL": "https://cuadrao.ai/privacidad"]
precondition(!CuadraoLegalURLs.configured(info: configuredValues).hasPages, "URLs alone do not enable links")
var enabledValues = configuredValues
for enabled in ["false", "", "$(ARGUS_CUADRAO_LEGAL_LINKS_ENABLED)"] {
    enabledValues["ARGUS_CUADRAO_LEGAL_LINKS_ENABLED"] = enabled
    precondition(!CuadraoLegalURLs.configured(info: enabledValues).hasPages)
}
enabledValues["ARGUS_CUADRAO_LEGAL_LINKS_ENABLED"] = "true"
let enabled = CuadraoLegalURLs.configured(info: enabledValues)
precondition(enabled.hasTermsAndPrivacy)
precondition(enabled.terms?.absoluteString == "https://cuadrao.ai/terminos")
precondition(enabled.privacy?.absoluteString == "https://cuadrao.ai/privacidad")
for key in ["ARGUS_CUADRAO_TERMS_URL", "ARGUS_CUADRAO_PRIVACY_URL"] {
    for value in ["", "$(UNSET)", "http://cuadrao.ai/terms", "https://user:password@cuadrao.ai/terms"] {
        var partial = enabledValues
        partial[key] = value
        precondition(!CuadraoLegalURLs.configured(info: partial).hasTermsAndPrivacy)
    }
    var missing = enabledValues
    missing.removeValue(forKey: key)
    precondition(!CuadraoLegalURLs.configured(info: missing).hasTermsAndPrivacy)
}
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
precondition(CuadraoLegalURLs.current(arguments: ["--cuadrao-legal-test-terms-only"]).terms != nil)
precondition(!CuadraoLegalURLs.current(arguments: ["--cuadrao-legal-test-terms-only"]).hasTermsAndPrivacy)
precondition(CuadraoLegalURLs.current(arguments: ["--cuadrao-legal-test-privacy-only"]).privacy != nil)
precondition(!CuadraoLegalURLs.current(arguments: ["--cuadrao-legal-test-privacy-only"]).hasTermsAndPrivacy)
precondition(overridden.hasPages)
precondition(overridden.hasTermsAndPrivacy, "both documents set supports the acceptance sentence")
#else
precondition(overridden == empty, "a Release build ignores the test argument")
#endif
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
