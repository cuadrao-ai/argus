"""Run the production debt draft directly, without an app or simulator."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="argus-debt-draft-tests-") as temporary:
    package = Path(temporary)
    source = package / "Sources/FinancialDebtModels"
    tests = package / "Tests/FinancialDebtDraftTests"
    source.mkdir(parents=True)
    prepare(root, source, package=True)
    tests.mkdir(parents=True)
    # Follow the existing model harness: copy the exact production declarations.
    shutil.copy(root / "ios/ArgusFoundation/Plan/FinancialDebtDraft.swift", source)
    shutil.copy(root / "ios/ArgusFoundation/Accounts/AccountEntry.swift", source)
    for filename, declaration, target in [
        (
            "Accounts/AccountsView.swift",
            "enum AccountPresentation {",
            "AccountPresentation.swift",
        ),
        (
            "Plan/FinancialPlanModel.swift",
            "enum PlanPresentation {",
            "PlanPresentation.swift",
        ),
    ]:
        text = (root / "ios/ArgusFoundation" / filename).read_text()
        (source / target).write_text(
            "import Foundation\nimport ArgusSession\n" + text[text.index(declaration) :]
        )
    shutil.copy(Path(__file__).with_name("FinancialDebtDraftTests.swift"), tests)
    dependency = root / "ios/Packages/ArgusSession"
    (package / "Package.swift").write_text(
        '''// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "FinancialDebtModels", defaultLocalization: "es-419", platforms: [.macOS(.v14)],
    dependencies: [.package(path: "'''
        + str(dependency)
        + """")], targets: [
    .target(name: "FinancialDebtModels", dependencies: [.product(name: "ArgusSession", package: "ArgusSession")], resources: [.process("Resources")]),
    .testTarget(name: "FinancialDebtDraftTests", dependencies: ["FinancialDebtModels", .product(name: "ArgusSession", package: "ArgusSession")])
])
"""
    )
    shutil.copy(dependency / "Package.resolved", package)
    subprocess.run(
        [
            "swift",
            "test",
            "--package-path",
            str(package),
            "--scratch-path",
            "/private/tmp/argus-debt-draft-build",
            "--disable-sandbox",
            "--disable-automatic-resolution",
        ],
        check=True,
    )
