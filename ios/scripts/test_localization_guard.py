"""Exercise the foundation guard through its public CLI and fixture files."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('localization_guard.py')


class LocalizationGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = self.root / 'ios/ArgusFoundation/Resources/Localizable.xcstrings'
        self.catalog.parent.mkdir(parents=True)
        self.payload = {
            'sourceLanguage': 'es-419', 'version': '1.0', 'strings': {
                'greeting': {'localizations': {
                    language: {'stringUnit': {'state': 'translated', 'value': value}}
                    for language, value in [('en', 'Hello'), ('es-419', 'Hola')]
                }}
            }
        }
        self.catalog.write_text(json.dumps(self.payload))
        self.registry = self.root / 'ios/scripts/localization_noncopy.json'
        self.registry.parent.mkdir(parents=True)
        self.registry.write_text('[]')
        self.source = self.root / 'ios/ArgusFoundation/Example.swift'
        self.source.write_text('Text("greeting")\n')

    def run_guard(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--root', str(self.root)],
            text=True, capture_output=True, check=False,
        )

    def test_known_key_is_clean(self):
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('0 error(s), 0 warning(s)', result.stdout)

    def test_unfinished_call_site_warns_and_succeeds(self):
        self.source.write_text('Text("Pending copy")\n')
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('WARNING:', result.stdout)
        self.assertIn('Pending copy', result.stdout)

    def test_registry_is_exact_for_path_and_literal(self):
        self.source.write_text('Text("USD")\nText("EUR")\n')
        self.registry.write_text(json.dumps([{
            'path': 'ios/ArgusFoundation/Example.swift',
            'literal': 'USD', 'reason': 'ISO currency code',
        }]))
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("literal 'USD'", result.stdout)
        self.assertIn("literal 'EUR'", result.stdout)
        self.source.rename(self.source.with_name('Other.swift'))
        self.assertIn("literal 'USD'", self.run_guard().stdout)

    def test_invalid_registry_fails(self):
        self.registry.write_text('[{"path":"../escape","literal":"USD","reason":""}]')
        self.assertEqual(self.run_guard().returncode, 1)

    def test_missing_translation_fails(self):
        del self.payload['strings']['greeting']['localizations']['en']
        self.catalog.write_text(json.dumps(self.payload))
        result = self.run_guard()
        self.assertEqual(result.returncode, 1)
        self.assertIn('missing translated en', result.stdout)

    def test_source_language_mutation_fails(self):
        self.payload['sourceLanguage'] = 'en'
        self.catalog.write_text(json.dumps(self.payload))
        self.assertEqual(self.run_guard().returncode, 1)

    def test_malformed_catalog_fails(self):
        self.catalog.write_text('{')
        self.assertEqual(self.run_guard().returncode, 1)


if __name__ == '__main__':
    unittest.main()
