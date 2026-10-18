"""Read only the age-gate build contract; never creates local signing or environment files."""
from pathlib import Path
import json
import plistlib
import subprocess

root = Path(__file__).resolve().parents[2]
assert "CODE_SIGN_ENTITLEMENTS = Config/SignInWithApple.entitlements" in (root / "ios/Config/Device.local.xcconfig.example").read_text()
for configuration, sdk, override, entitlement in [
    ("Debug", "iphonesimulator", None, "Config/Simulator.entitlements"),
    ("Release", "iphoneos", None, "Config/DeclaredAgeRange.entitlements"),
    ("Debug", "iphoneos", "CODE_SIGN_ENTITLEMENTS=Config/SignInWithApple.entitlements", "Config/SignInWithApple.entitlements"),
]:
    command = ["xcodebuild", "-project", str(root / "ios/ArgusFoundation.xcodeproj"), "-scheme", "ArgusFoundation",
               "-configuration", configuration, "-sdk", sdk, "-showBuildSettings", "-json"]
    if sdk == "iphoneos":
        command.extend(["SUPPORTED_PLATFORMS=iphoneos", "SDKROOT=iphoneos"])
    if override:
        command.append(override)
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    settings = next(item["buildSettings"] for item in json.loads(result.stdout) if item["target"] == "ArgusFoundation")
    assert settings["IPHONEOS_DEPLOYMENT_TARGET"] == "17.0"
    assert settings["CODE_SIGN_ENTITLEMENTS"] == entitlement, (sdk, settings["CODE_SIGN_ENTITLEMENTS"])
    payload = plistlib.loads((root / "ios" / entitlement).read_bytes())
    assert payload["com.apple.developer.declared-age-range"] is True
    if "SignInWithApple" in entitlement:
        assert payload["com.apple.developer.applesignin"] == ["Default"]
    if configuration == "Release":
        for key in ("ARGUS_APPLE_SIGN_IN_ENABLED", "ARGUS_GOOGLE_SIGN_IN_ENABLED", "ARGUS_CUADRAO_LEGAL_LINKS_ENABLED"):
            assert settings[key] == "false", key
    print(f"{configuration} {sdk}: deployment 17.0, {entitlement}, age entitlement present")
