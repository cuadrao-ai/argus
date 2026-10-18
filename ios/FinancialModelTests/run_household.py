"""Exercise the actual Household presentation model with controlled transport delays."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LocalizationTests"))
from support import prepare

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="argus-household-models-") as temporary:
    package = Path(temporary)
    source = package / "Sources/FinancialModels"
    tests = package / "Tests/FinancialModelTests"
    source.mkdir(parents=True)
    prepare(root, source, package=True)
    tests.mkdir(parents=True)
    shutil.copy(root / "ios/ArgusFoundation/Household/HouseholdModel.swift", source)
    shutil.copy(root / "ios/ArgusFoundation/Connected/ConnectedSpacesPolicy.swift", source)
    shutil.copy(root / "ios/ArgusFoundation/Household/HouseholdPlanModel.swift", source)
    shutil.copy(root / "ios/ArgusFoundation/Accounts/AccountEntry.swift", source)
    editor = (
        root / "ios/ArgusFoundation/Household/HouseholdActivityEditor.swift"
    ).read_text()
    (source / "HouseholdActivityEditor.swift").write_text(
        editor[: editor.index("struct HouseholdActivityEditorView:")]
    )
    contribution = (root / "ios/ArgusFoundation/Household/HouseholdContributionEditor.swift").read_text()
    (source / "HouseholdContributionEditor.swift").write_text(contribution[:contribution.index("struct HouseholdContributionEditorView:")])
    views = (root / "ios/ArgusFoundation/Household/HouseholdViews.swift").read_text()
    plan_views = (root / "ios/ArgusFoundation/Household/HouseholdPlanViews.swift").read_text()
    people = (root / "ios/ArgusFoundation/Household/HouseholdPlanPeople.swift").read_text()
    definition_editor = (root / "ios/ArgusFoundation/Household/HouseholdPlanDefinitionEditor.swift").read_text()
    (source / "HouseholdPlanDefinitionEdit.swift").write_text("import Foundation\nimport ArgusSession\n" + definition_editor[definition_editor.index("enum HouseholdPlanDefinitionEdit {"):])
    (source / "HouseholdPlanPresentation.swift").write_text("import Foundation\nimport ArgusSession\n" + plan_views[plan_views.index("enum HouseholdPlanPresentation {"):] + "\n" + people[people.index("enum PlanDate {"):] + "\n" + views[views.index("enum HouseholdMoney {"):views.index("struct HouseholdConnectedDestination:")])
    presentation = (root / "ios/ArgusFoundation/Accounts/AccountsView.swift").read_text()
    (source / "AccountPresentation.swift").write_text(
        "import Foundation\nimport ArgusSession\n"
        + presentation[presentation.index("enum AccountPresentation {") :]
    )
    shutil.copy(
        root / "ios/Packages/ArgusSession/Tests/ArgusSessionTests/TestSupport.swift",
        tests,
    )
    shutil.copy(Path(__file__).with_name("HouseholdModelTests.swift"), tests)
    shutil.copy(Path(__file__).with_name("HouseholdPlanModelTests.swift"), tests)
    wire_tests = (root / "ios/Packages/ArgusSession/Tests/ArgusSessionTests/HouseholdPlanTests.swift").read_text()
    (tests / "SharedPlanTestData.swift").write_text("import Foundation\nimport ArgusSession\n" + wire_tests[wire_tests.index("enum SharedPlanTestData {"):])
    (package / "Package.swift").write_text(
        '''// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "FinancialModels", defaultLocalization: "es-419", platforms: [.macOS(.v14)], dependencies: [
    .package(path: "'''
        + str(root / "ios/Packages/ArgusSession")
        + """"),
    .package(url: "https://github.com/supabase/supabase-swift.git", exact: "2.55.2")
], targets: [
    .target(name: "FinancialModels", dependencies: [.product(name: "ArgusSession", package: "ArgusSession")], resources: [.process("Resources")]),
    .testTarget(name: "FinancialModelTests", dependencies: ["FinancialModels", .product(name: "ArgusSession", package: "ArgusSession"), .product(name: "Auth", package: "supabase-swift")])
])
"""
    )
    shutil.copy(
        root / "ios/Packages/ArgusSession/Package.resolved", package / "Package.resolved"
    )
    scratch = Path(
        os.environ.get(
            "ARGUS_HOUSEHOLD_MODEL_SCRATCH_PATH",
            root / "ios/.build/household-model-tests",
        )
    )
    cache_args = []
    if cache := os.environ.get("ARGUS_SWIFT_CACHE_PATH"):
        cache_args = ["--cache-path", cache]
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
            *cache_args,
        ],
        check=True,
    )
