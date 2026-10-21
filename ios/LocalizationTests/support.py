"""Give isolated Swift check executables the app's exact localization resources."""
import json
from pathlib import Path


def prepare(root: Path, folder: Path, package: bool = False) -> Path:
    catalog = json.loads((root / 'ios/ArgusFoundation/Resources/Localizable.xcstrings').read_text())
    resource_root = folder / 'Resources' if package else folder
    for language in ('es-419', 'en'):
        locale = resource_root / (language + '.lproj')
        locale.mkdir(parents=True, exist_ok=True)
        values = []
        for key, entry in catalog['strings'].items():
            value = entry['localizations'][language]['stringUnit']['value']
            values.append(json.dumps(key, ensure_ascii=False) + ' = ' + json.dumps(value, ensure_ascii=False) + ';')
        (locale / 'Localizable.strings').write_text('\n'.join(values) + '\n')
    helper = folder / 'CuadraoCopy.swift'
    text = (root / 'ios/ArgusFoundation/CuadraoCopy.swift').read_text()
    if package:
        text = text.replace('Bundle.main', 'Bundle.module')
    helper.write_text(text)
    return helper
