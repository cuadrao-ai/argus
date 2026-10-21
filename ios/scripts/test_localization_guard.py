import json
from pathlib import Path
import tempfile
import unittest

import localization_base_copy as base_copy
import localization_guard as guard


class LocalizationGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'ios/ArgusFoundation/Screen.swift'
        self.source.parent.mkdir(parents=True)
        for path in (guard.CATALOG, Path('ios/ArgusFoundation/Resources/InfoPlist.xcstrings'), Path('ios/Config/Info.plist')):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((guard.ROOT / path).read_bytes())

    def assertLeaks(self, source):
        self.source.write_text(source)
        self.assertTrue(guard.check(self.root), source)

    def test_catalog_use_passes(self):
        self.source.write_text('Text("destination.home")\nText(CuadraoCopy.text("destination.home", spanish: true))')
        self.assertEqual(guard.check(self.root), [])

    def test_interpolated_brand_fails(self):
        self.assertLeaks('Text("\\(flag ? "Argus" : "Cuadrao")")')

    def test_english_ui_literal_fails(self):
        self.assertLeaks('Text("Hello world")')

    def test_single_word_label_fails(self):
        self.assertLeaks('Button("Hello") {}')

    def test_model_title_brand_fails(self):
        self.assertLeaks('var title: String { "Argus" }\nText(title)')

    def test_model_title_single_word_fails(self):
        self.assertLeaks('var title: String {\n "Hello"\n}\nText(title)')

    def test_custom_group_fails(self):
        self.assertLeaks('group("App") { Text(user.name) }')

    def test_value_title_closure_fails(self):
        self.assertLeaks('CuadraoChoiceMenu(valueTitle: { value in\n value ? "Balance" : "Spending"\n})')

    def test_visible_url_fails(self):
        self.assertLeaks('Text("https://example.com")')

    def test_verbatim_catalog_key_fails(self):
        self.assertLeaks('Text(verbatim: "destination.home")')

    def test_standalone_catalog_prefix_fails(self):
        self.assertLeaks('Text("accounts.type.")')

    def test_composed_localized_key_passes(self):
        self.source.write_text('Text(LocalizedStringKey("accounts.type." + account.type))')
        self.assertEqual(guard.check(self.root), [])

    def test_missing_catalog_key_fails(self):
        self.assertLeaks('Text(CuadraoCopy.text("missing.key", spanish: true))')

    def test_symbol_and_identifiers_pass(self):
        self.source.write_text('Image(systemName: "person.crop.circle")\nText(user.name).accessibilityIdentifier("internal.argus.name")')
        self.assertEqual(guard.check(self.root), [])

    def test_diagnostics_pass(self):
        self.source.write_text('ScanTrace.mark("scanner closed")\nfatalError("Not implemented")')
        self.assertEqual(guard.check(self.root), [])

    def test_comments_do_not_leak(self):
        self.source.write_text('// Text("Argus")\n/* Text("Hello") */')
        self.assertEqual(guard.check(self.root), [])

    def test_catalog_brand_fails(self):
        path = self.root / guard.CATALOG
        catalog = json.loads(path.read_text())
        catalog['strings']['destination.home']['localizations']['es-419']['stringUnit']['value'] = 'Argus'
        path.write_text(json.dumps(catalog))
        self.assertTrue(any('branding' in error for error in guard.check(self.root)))

    def test_registered_technical_literal_cannot_become_copy(self):
        for literal, original, injected in [
            ('"liability"', 'let kind = "liability"', 'Text("liability")'),
            ('"archivebox"', 'Image(systemName: "archivebox")', 'Button("archivebox") {}'),
            ('"argus.session"', 'let storage = "argus.session"', 'Text("argus.session")'),
        ]:
            self.source.write_text(original)
            path = self.root / guard.EXCEPTIONS
            path.parent.mkdir(parents=True, exist_ok=True)
            offset = original.index(literal)
            path.write_text(json.dumps({guard.identity(Path('ios/ArgusFoundation/Screen.swift'), literal): {
                'literal': literal, 'reason': 'Internal technical literal', 'contexts': [guard.context(original, offset)]
            }}))
            self.assertEqual(guard.check(self.root), [])
            self.assertLeaks(original + '\n' + injected)

    def test_permission_coverage_fails(self):
        path = self.root / 'ios/ArgusFoundation/Resources/InfoPlist.xcstrings'
        catalog = json.loads(path.read_text())
        del catalog['strings']['NSCameraUsageDescription']
        path.write_text(json.dumps(catalog))
        self.assertTrue(any('NSCameraUsageDescription' in error for error in guard.check(self.root)))

    def test_noncopy_exception_is_exact(self):
        raw = '"Synthetic fixture"'
        path = self.root / guard.EXCEPTIONS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({guard.identity(Path('ios/ArgusFoundation/Screen.swift'), raw): {'literal': raw, 'reason': 'Synthetic test fixture', 'contexts': [guard.context('Text(' + raw + ')', 5)]}}))
        self.source.write_text('Text(' + raw + ')')
        self.assertEqual(guard.check(self.root), [])
        self.assertLeaks('Text("New unapproved label")')


class BaseCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.base = base_copy.load_base(guard.ROOT)
        except base_copy.BaseUnavailable as error:
            raise unittest.SkipTest(str(error))
        cls.catalog = json.loads((guard.ROOT / guard.CATALOG).read_text())

    def kinds(self, catalog):
        return {finding.key: finding for finding in base_copy.compare(catalog, self.base)}

    def test_catalog_keeps_every_spanish_value_the_base_shipped(self):
        replaced = [finding for finding in self.kinds(self.catalog).values() if finding.kind in ('replaced', 'ambiguous')]
        self.assertEqual(replaced, [])

    def test_english_copied_over_base_spanish_is_reported(self):
        catalog = json.loads(json.dumps(self.catalog))
        for key in ('copy.guestReceipts.afcc90c7b0', 'destination.home'):
            entry = catalog['strings'][key]['localizations']
            entry['es-419']['stringUnit']['value'] = entry['en']['stringUnit']['value']
        findings = self.kinds(catalog)
        self.assertEqual(findings['copy.guestReceipts.afcc90c7b0'].kind, 'replaced')
        self.assertEqual(findings['copy.guestReceipts.afcc90c7b0'].base_es, 'Aún no hay recibos.')
        self.assertEqual(findings['destination.home'].kind, 'replaced')

    def test_english_only_base_label_stays_pending(self):
        self.assertEqual(self.kinds(self.catalog)['copy.cuadraoSpendingTrends.aee00efaba'].kind, 'todo')

    def test_inline_pair_forms_are_read(self):
        source = '''
            Text(spanish ? "Hola \\(name)" : "Hello \\(name)")
            let note = es ? (count == 1 ? "1 recibo" : "\\(count) recibos") : (count == 1 ? "1 receipt" : "\\(count) receipts")
            Label(text("Permiso guardado", "Permission saved"), systemImage: "checkmark")
            .init(spanish: "Servicios de casa", english: "Household bills")
            Text(spanish ? "\\(elapsed) \\(elapsed == 1 ? "día" : "días")" : "\\(elapsed) \\(elapsed == 1 ? "day" : "days")")
        '''
        pairs = {(pair.es, pair.en) for pair in base_copy.pairs('Screen.swift', source)}
        self.assertEqual(pairs, {
            ('Hola %1$@', 'Hello %1$@'), ('1 recibo', '1 receipt'), ('%1$@ recibos', '%1$@ receipts'),
            ('Permiso guardado', 'Permission saved'), ('Servicios de casa', 'Household bills'),
            ('%1$@ %2$@', '%1$@ %2$@'), ('día', 'day'), ('días', 'days'),
        })


if __name__ == '__main__':
    unittest.main()
