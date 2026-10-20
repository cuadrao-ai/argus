"""Compile the real capture adapters for a coordinator-approved iOS Simulator."""
from pathlib import Path
import argparse
import os
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--simulator", help="Run only on a simulator assigned by the coordinator")
parser.add_argument("--release", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
receipts = root / "ios/ArgusFoundation/Cuadrao/Receipts"
folder = root / "ios/.build/scan-capture" / ("release" if args.release else "debug")
folder.mkdir(parents=True, exist_ok=True)
capture = (receipts / "CuadraoReceiptCapture.swift").read_text()
error = (receipts / "CuadraoReceipt.swift").read_text()
declarations = capture[capture.index("enum ReceiptSourceChoice:"):capture.index("struct ReceiptSourceActions:")]
declarations += capture[capture.index("typealias ReceiptCapturedFiles ="):capture.index("struct CuadraoReceiptCapture:")]
declarations += error[error.index("enum ReceiptError:"):error.index("struct ReceiptSample {")]
support = folder / "CaptureTypes.swift"
support.write_text("import Foundation\n" + declarations)
shell = (root / "ios/ArgusFoundation/Connected/ConnectedCuadraoShell.swift").read_text()
dismiss = shell.split('ScanTrace.mark("scanner closed")', 1)[1].split("}) { source in", 1)[0]
callback = shell.split("ReceiptNativePicker(source: source, spanish: spanish) { result in", 1)[1].split("}.ignoresSafeArea()", 1)[0]
handoff = folder / "CapturePresentation.swift"
handoff.write_text('''import Foundation
@MainActor final class CapturePresentation {
    var capturing: ReceiptSourceChoice? = .scan
    var captured: ReceiptCapturedFiles?
    var consumed: [ReceiptCapturedFiles] = []
    let spanish = false
    let auth = CaptureAuth()
    func keep(_ files: ReceiptCapturedFiles) { consumed.append(files) }
    func dismissed() {
''' + dismiss + '''
    }
    func complete(_ result: Result<ReceiptCapturedFiles, Error>, source: ReceiptSourceChoice) {
''' + callback + '''
    }
}
@MainActor final class CaptureAuth {
    let savedReceipts: CaptureFailure? = CaptureFailure()
}
@MainActor final class CaptureFailure {
    enum Failure { case unusableFile }
    var count = 0
    func fail(_ error: Failure) { count += 1 }
}
''')
sdk = subprocess.check_output(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-path"], text=True).strip()
binary = folder / "checks"
command = ["xcrun", "swiftc", "-parse-as-library", "-sdk", sdk,
           "-target", "arm64-apple-ios17.0-simulator", "-module-cache-path", str(folder / "modules")]
if not args.release:
    command += ["-D", "DEBUG"]
command += [str(support), str(handoff), str(receipts / "CuadraoReceiptNativePicker.swift"),
            str(receipts / "ScanStub.swift"), str(receipts / "ScanTrace.swift"),
            str(root / "ios/ArgusFoundation/Connected/SavedReceiptFiles.swift"),
            str(Path(__file__).with_name("ScanCaptureChecks.swift")), "-o", str(binary)]
subprocess.run(command, check=True, env={**os.environ, "SDKROOT": sdk})
if args.release:
    strings = subprocess.check_output(["strings", str(binary)], text=True)
    assert "scan.stub.done" not in strings and "--cuadrao-scan-stub" not in strings
    assert "scan-trace.txt" not in strings
    print("Release has no scan stub entry or trace file writer.")
if args.simulator:
    subprocess.run(["xcrun", "simctl", "spawn", args.simulator, str(binary)], check=True)
else:
    print("Compiled only. No simulator was started.")
