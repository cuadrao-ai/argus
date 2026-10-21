"""Compile the real catalog and lookup helper, then exercise local behavior."""
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='cuadrao-localization-') as directory:
    folder = Path(directory)
    catalog = json.loads((root / 'ios/ArgusFoundation/Resources/Localizable.xcstrings').read_text())
    for key, es, en in [('localization.test.format', '%2$@, %1$@: 50%%', '%2$@, %1$@: 50%%'), ('localization.test.percent', '50%%', '50%%')]:
        catalog['strings'][key] = {'extractionState': 'manual', 'localizations': {language: {'stringUnit': {'state': 'translated', 'value': value}} for language, value in [('es-419', es), ('en', en)]}}
    source = folder / 'Localizable.xcstrings'
    source.write_text(json.dumps(catalog))
    subprocess.run(['xcrun', 'xcstringstool', 'compile', '--output-directory', str(folder), str(source)], check=True)
    executable = folder / 'localization-tests'
    subprocess.run(['xcrun', 'swiftc', '-module-cache-path', str(folder / 'ModuleCache'), str(root / 'ios/ArgusFoundation/CuadraoCopy.swift'), str(root / 'ios/ArgusFoundation/Accounts/AccountEntry.swift'), str(Path(__file__).with_name('main.swift')), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
