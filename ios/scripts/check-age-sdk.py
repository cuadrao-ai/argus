"""The age gate keeps iOS 17 deployment but compiles the regulatory API with an iOS 26.4+ SDK."""
import subprocess

version = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-version"], text=True).strip()
parts = tuple(int(part) for part in version.split(".")[:2])
if parts < (26, 4):
    raise SystemExit(f"Declared Age Range regulatory symbols require iOS SDK 26.4 or newer, found {version}")
print(f"Declared Age Range SDK passed: iOS {version}; deployment floor remains iOS 17")
