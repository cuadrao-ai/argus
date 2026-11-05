import argparse
import copy
import plistlib
import unittest
from pathlib import Path

REASONS = {
    "NSPrivacyAccessedAPICategoryUserDefaults": ["CA92.1"],
    "NSPrivacyAccessedAPICategorySystemBootTime": ["35F9.1"],
}
ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "ios/ArgusFoundation/PrivacyInfo.xcprivacy"


def validate(payload):
    if set(payload) != {"NSPrivacyAccessedAPITypes"}:
        raise ValueError("This reason-only manifest must not assert collection or tracking facts")
    entries = payload["NSPrivacyAccessedAPITypes"]
    declarations = {}
    for entry in entries:
        if set(entry) != {"NSPrivacyAccessedAPIType", "NSPrivacyAccessedAPITypeReasons"}:
            raise ValueError("Unexpected required-reason entry fields")
        category = entry["NSPrivacyAccessedAPIType"]
        if category in declarations:
            raise ValueError("Duplicate required-reason category")
        declarations[category] = entry["NSPrivacyAccessedAPITypeReasons"]
    if declarations != REASONS:
        raise ValueError("Declarations do not match the audited app uses")


class ManifestChecks(unittest.TestCase):
    def setUp(self):
        self.payload = plistlib.loads(SOURCE.read_bytes())

    def test_source_manifest(self):
        validate(self.payload)

    def test_packaged_manifest(self):
        packaged = plistlib.loads((APP / "PrivacyInfo.xcprivacy").read_bytes())
        validate(packaged)
        self.assertEqual(self.payload, packaged)

    def test_missing_category_rejected(self):
        self.payload["NSPrivacyAccessedAPITypes"].pop()
        with self.assertRaises(ValueError):
            validate(self.payload)

    def test_wrong_reason_rejected(self):
        self.payload["NSPrivacyAccessedAPITypes"][0]["NSPrivacyAccessedAPITypeReasons"] = ["1C8F.1"]
        with self.assertRaises(ValueError):
            validate(self.payload)

    def test_duplicate_category_rejected(self):
        self.payload["NSPrivacyAccessedAPITypes"].append(copy.deepcopy(self.payload["NSPrivacyAccessedAPITypes"][0]))
        with self.assertRaises(ValueError):
            validate(self.payload)

    def test_unverified_tracking_claim_rejected(self):
        self.payload["NSPrivacyTracking"] = False
        with self.assertRaises(ValueError):
            validate(self.payload)

    def test_no_declarations_rejected(self):
        with self.assertRaises(ValueError):
            validate({})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    APP = parser.parse_args().app
    unittest.main(argv=[__file__], verbosity=2)
