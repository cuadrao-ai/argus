"""Record only the app-visible horizontal/vertical gesture proof on an owned device.

Run from repository root after capture-evidence.sh has built the current source:
python3 docs/reports/evidence/chart-validation/ios/record-motion.py OWNED_UDID
"""
import json
import pathlib
import signal
import subprocess
import sys
import time

owned_device = sys.argv[1]
evidence = pathlib.Path(__file__).resolve().parent
result_path = f"/tmp/argus-chart-ios-motion-{int(time.time())}.xcresult"
video = evidence / "scrub-and-scroll.mp4"
command = [
    "xcodebuild", "-project", "prototypes/chart-validation/ios/ChartPrototype.xcodeproj",
    "-scheme", "ChartPrototype", "-sdk", "iphonesimulator",
    "-destination", f"id={owned_device}", "-derivedDataPath", "/tmp/argus-chart-ios",
    "-resultBundlePath", result_path, "test-without-building", "CODE_SIGNING_ALLOWED=NO",
    "-parallel-testing-enabled", "NO",
    "-only-testing:ChartPrototypeUITests/ChartUITests/testHorizontalReleaseAndVerticalScroll",
]
recorder = None
started = False
finished = False
with (evidence / "motion-test.log").open("w") as receipt:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for line in process.stdout:
            receipt.write(line.rstrip() + "\n")
            receipt.flush()
            if not started and 'Press "financialChart" Other[0.20' in line:
                recorder = subprocess.Popen([
                    "xcrun", "simctl", "io", owned_device, "recordVideo", "--codec=h264",
                    "--force", str(video)
                ], stdout=receipt, stderr=receipt)
                started = True
            if recorder and "Added attachment named 'vertical-scroll'" in line:
                recorder.send_signal(signal.SIGINT)
                recorder.wait(timeout=20)
                recorder = None
                finished = True
        status = process.wait()
    finally:
        if recorder:
            recorder.send_signal(signal.SIGINT)
            recorder.wait(timeout=20)
if status != 0 or not (started and finished):
    raise SystemExit(f"Motion proof incomplete: test={status}, started={started}, finished={finished}")
(evidence / "motion-identity.json").write_text(json.dumps({
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "device": owned_device,
    "test_result_bundle": result_path,
    "recording": video.name,
    "scope": "App-only horizontal scrub and vertical page scroll; XCTest drives real simulator gestures",
}, indent=2) + "\n")
print(f"PASS: app-only gesture recording {video}")
