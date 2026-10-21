"""Exercise the actual invitations presentation model on the host over a contract-shaped transport."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="argus-invitation-models-") as temporary:
    package = Path(temporary)
    source = package / "Sources/InvitationModels"
    tests = package / "Tests/InvitationModelTests"
    source.mkdir(parents=True)
    prepare(root, source, package=True)
    tests.mkdir(parents=True)
    shutil.copy(root / "ios/ArgusFoundation/Invitations/InvitationsModel.swift", source)
    shutil.copy(Path(__file__).with_name("InvitationsModelTests.swift"), tests)
    (package / "Package.swift").write_text(
        '''// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "InvitationModels", defaultLocalization: "es-419", platforms: [.macOS(.v14)], dependencies: [
    .package(path: "'''
        + str(root / "ios/Packages/ArgusSession")
        + """")
], targets: [
    .target(name: "InvitationModels", dependencies: [.product(name: "ArgusSession", package: "ArgusSession")], resources: [.process("Resources")]),
    .testTarget(name: "InvitationModelTests", dependencies: ["InvitationModels", .product(name: "ArgusSession", package: "ArgusSession")])
])
"""
    )
    shutil.copy(
        root / "ios/Packages/ArgusSession/Package.resolved", package / "Package.resolved"
    )
    scratch = Path(
        os.environ.get(
            "ARGUS_INVITATION_MODEL_SCRATCH_PATH",
            root / "ios/.build/invitation-model-tests",
        )
    )
    subprocess.run(
        [
            "swift",
            "test",
            "--package-path",
            str(package),
            "--scratch-path",
            str(scratch),
            "--disable-sandbox",
            "--disable-automatic-resolution",
        ],
        check=True,
    )
