"""Test the actual native presentation models without changing signing/project files."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
subprocess.run(["python3", str(root / "ios/DesignPreviewTests/run_no_keyboard_accessory.py")], check=True)
with tempfile.TemporaryDirectory(prefix="argus-financial-models-") as temporary:
    package = Path(temporary)
    source = package / "Sources/FinancialModels"
    tests = package / "Tests/FinancialModelTests"
    source.mkdir(parents=True)
    tests.mkdir(parents=True)
    for name in ("AccountsModel.swift", "FinancialLoopModel.swift", "FinancialObservationRead.swift", "FinancialActivityEditor.swift", "AccountEntry.swift"):
        shutil.copy(root / "ios/ArgusFoundation/Accounts" / name, source / name)
    asset = (root / "ios/ArgusFoundation/Accounts/FinancialAssetEditor.swift").read_text()
    (source / "FinancialAssetEditor.swift").write_text(asset)
    form = (root / "ios/ArgusFoundation/Accounts/FinancialAssetForm.swift").read_text()
    percent = form[form.index("    static func percent("):form.index("    var body:", form.index("struct AssetShareControl:"))]
    (source / "AssetShareControl.swift").write_text("import Foundation\nenum AssetShareControl {\n" + percent + "}\n")
    for name in ("FinancialPlanModel.swift", "FinancialBudgetModel.swift", "FinancialGoalModel.swift", "FinancialDebtModel.swift"):
        shutil.copy(root / "ios/ArgusFoundation/Plan" / name, source / name)
    for name in ("FinancialGoalDraft.swift", "FinancialDebtDraft.swift"):
        shutil.copy(root / "ios/ArgusFoundation/Plan" / name, source / name)
    shutil.copy(root / "ios/ArgusFoundation/Plan/ConnectedPlanMapping.swift", source / "ConnectedPlanMapping.swift")
    plans = (root / "ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanPreview.swift").read_text()
    (source / "CanvasPlan.swift").write_text("import Foundation\n" + plans[plans.index("enum CanvasPlanKind:"):plans.index("@Observable final class CuadraoPlanPreview {")])
    shutil.copy(root / "ios/ArgusFoundation/Search/FinancialSearchModel.swift", source / "FinancialSearchModel.swift")
    shutil.copy(root / "ios/ArgusFoundation/Auth/AccountDeletionModel.swift", source / "AccountDeletionModel.swift")
    shutil.copy(root / "ios/ArgusFoundation/ReleaseUI/Identity/ReleaseIdentityModels.swift", source / "ReleaseIdentityModels.swift")
    shutil.copy(root / "ios/ArgusFoundation/FinancialScrollRestoration.swift", source / "FinancialScrollRestoration.swift")
    # The formatter remains one production source; copy its exact declaration.
    presentation = (root / "ios/ArgusFoundation/Accounts/AccountsView.swift").read_text()
    (source / "AccountPresentation.swift").write_text("import Foundation\nimport ArgusSession\n" + presentation[presentation.index("enum AccountPresentation {"):])
    canvas = root / "ios/ArgusFoundation/Cuadrao"
    kinds = (canvas / "CuadraoAccountsPreview.swift").read_text()
    (source / "CanvasAccountKind.swift").write_text("import Foundation\n" + kinds[kinds.index("enum CanvasAccountKind:"):kinds.index("struct CanvasAccount:")])
    entry = (canvas / "CuadraoFirstAccountSheet.swift").read_text()
    (source / "CanvasAccountEntry.swift").write_text("import Foundation\n" + entry[entry.index("struct CanvasAccountEntry:"):entry.index("struct CanvasAccountEntryIDs {")])
    values = (canvas / "CanvasAccountPresentation.swift").read_text()
    declarations = [("struct CanvasAccountRowValue {", "struct CanvasAccountRowContent:"),
                    ("struct CanvasAccountDetailValue {", "struct CanvasAccountDetailHeader:")]
    (source / "CanvasAccountDisplayValues.swift").write_text("import Foundation\n" + "\n".join(
        values[values.index(start):values.index(end)] for start, end in declarations))
    connected = (root / "ios/ArgusFoundation/Connected/ConnectedAccountPresentation.swift").read_text()
    (source / "ConnectedAccountPresentation.swift").write_text("import Foundation\nimport ArgusSession\n@MainActor\n" + connected[connected.index("enum ConnectedAccountPresentation {"):])
    shutil.copy(root / "ios/ArgusFoundation/Accounts/FinancialActivityPresentation.swift", source / "FinancialActivityPresentation.swift")
    history = (canvas / "CuadraoBalanceHistory.swift").read_text()
    (source / "CanvasBalancePoint.swift").write_text("import Foundation\n" + history[history.index("struct CanvasBalancePoint:"):history.index("enum CanvasBalanceHistory {")])
    shutil.copy(root / "ios/ArgusFoundation/Connected/ConnectedBalanceHistory.swift", source / "ConnectedBalanceHistory.swift")
    shutil.copy(root / "ios/ArgusFoundation/Plan/ConnectedForecastSeries.swift", source / "ConnectedForecastSeries.swift")
    shutil.copy(canvas / "Planning/PlanScenario.swift", source / "PlanScenario.swift")
    shutil.copy(root / "ios/ArgusFoundation/Connected/ConnectedAccountOrder.swift", source / "ConnectedAccountOrder.swift")
    shutil.copy(root / "ios/ArgusFoundation/Connected/ConnectedAddMovement.swift", source / "ConnectedAddMovement.swift")
    shutil.copy(root / "ios/ArgusFoundation/Connected/SavedReceiptsModel.swift", source / "SavedReceiptsModel.swift")
    shutil.copy(root / "ios/ArgusFoundation/Connected/SavedReceiptCopy.swift", source / "SavedReceiptCopy.swift")
    shutil.copy(root / "ios/ArgusFoundation/Connected/ReceiptJourneyModel.swift", source / "ReceiptJourneyModel.swift")
    shutil.copy(root / "ios/ArgusFoundation/Connected/ReceiptJourneyTransport.swift", source / "ReceiptJourneyTransport.swift")
    shutil.copy(root / "ios/ArgusFoundation/Connected/ReceiptReviewDraft.swift", source / "ReceiptReviewDraft.swift")
    shutil.copy(root / "ios/ArgusFoundation/Connected/ReceiptSearch.swift", source / "ReceiptSearch.swift")
    shutil.copy(canvas / "CuadraoNavigationSlot.swift", source / "CuadraoNavigationSlot.swift")
    shutil.copy(root / "ios/ArgusFoundation/Guest/GuestAccessPolicy.swift", source / "GuestAccessPolicy.swift")
    shutil.copy(root / "ios/ArgusFoundation/Guest/GuestReceiptStore.swift", source / "GuestReceiptStore.swift")
    shutil.copy(root / "ios/ArgusFoundation/Auth/CaptchaFramePolicy.swift", source / "CaptchaFramePolicy.swift")
    shutil.copy(root / "ios/ArgusFoundation/Plan/ConnectedPlanScenario.swift", source / "ConnectedPlanScenario.swift")
    shutil.copy(root / "ios/Packages/ArgusSession/Tests/ArgusSessionTests/TestSupport.swift", tests / "TestSupport.swift")
    shutil.copy(Path(__file__).with_name("FinancialModelTests.swift"), tests / "FinancialModelTests.swift")
    shutil.copy(Path(__file__).with_name("FinancialScrollRestorationTests.swift"), tests / "FinancialScrollRestorationTests.swift")
    shutil.copy(Path(__file__).with_name("ConnectedDetailPresentationTests.swift"), tests / "ConnectedDetailPresentationTests.swift")
    shutil.copy(Path(__file__).with_name("FinancialObservationReadTests.swift"), tests / "FinancialObservationReadTests.swift")
    shutil.copy(Path(__file__).with_name("AccountDeletionModelTests.swift"), tests / "AccountDeletionModelTests.swift")
    shutil.copy(Path(__file__).with_name("ConnectedBalanceHistoryTests.swift"), tests / "ConnectedBalanceHistoryTests.swift")
    shutil.copy(Path(__file__).with_name("ConnectedForecastSeriesTests.swift"), tests / "ConnectedForecastSeriesTests.swift")
    shutil.copy(Path(__file__).with_name("PlanScenarioTests.swift"), tests / "PlanScenarioTests.swift")
    shutil.copy(Path(__file__).with_name("ConnectedAccountOrderTests.swift"), tests / "ConnectedAccountOrderTests.swift")
    shutil.copy(Path(__file__).with_name("ConnectedReleaseSurfaceTests.swift"), tests / "ConnectedReleaseSurfaceTests.swift")
    shutil.copy(Path(__file__).with_name("GuestAccessPolicyTests.swift"), tests / "GuestAccessPolicyTests.swift")
    shutil.copy(Path(__file__).with_name("GuestReceiptStoreTests.swift"), tests / "GuestReceiptStoreTests.swift")
    shutil.copy(Path(__file__).with_name("CaptchaFramePolicyTests.swift"), tests / "CaptchaFramePolicyTests.swift")
    shutil.copy(Path(__file__).with_name("SavedReceiptsModelTests.swift"), tests / "SavedReceiptsModelTests.swift")
    shutil.copy(Path(__file__).with_name("ReceiptJourneyModelTests.swift"), tests / "ReceiptJourneyModelTests.swift")
    shutil.copy(Path(__file__).with_name("ReceiptSearchTests.swift"), tests / "ReceiptSearchTests.swift")
    shutil.copy(Path(__file__).with_name("ConnectedPlanMappingTests.swift"), tests / "ConnectedPlanMappingTests.swift")
    (package / "Package.swift").write_text('''// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "FinancialModels", platforms: [.macOS(.v14)], dependencies: [
    .package(path: "''' + str(root / "ios/Packages/ArgusSession") + '''"),
    .package(path: "''' + str(root / "ios/Packages/CuadraoBook") + '''"),
    .package(url: "https://github.com/supabase/supabase-swift.git", exact: "2.55.2")
], targets: [
    .target(name: "FinancialModels", dependencies: [.product(name: "ArgusSession", package: "ArgusSession"), .product(name: "CuadraoBook", package: "CuadraoBook")]),
    .testTarget(name: "FinancialModelTests", dependencies: ["FinancialModels", .product(name: "ArgusSession", package: "ArgusSession"), .product(name: "Auth", package: "supabase-swift")])
])
''')
    shutil.copy(root / "ios/Packages/ArgusSession/Package.resolved", package / "Package.resolved")
    scratch = Path(os.environ.get("ARGUS_FINANCIAL_MODEL_SCRATCH_PATH", root / "ios/.build/financial-model-tests"))
    command = ["swift", "test", "--package-path", str(package), "--scratch-path", str(scratch)]
    if cache := os.environ.get("ARGUS_SWIFT_CACHE_PATH"):
        command += ["--cache-path", cache]
    if os.environ.get("ARGUS_SWIFT_DISABLE_SANDBOX") == "1":
        command += ["--disable-sandbox", "--disable-automatic-resolution"]
    if selection := os.environ.get("ARGUS_FINANCIAL_MODEL_TEST_FILTER"):
        command += ["--filter", selection]
    subprocess.run(command, check=True, env={**os.environ, "ARGUS_REPO_ROOT": str(root)})
