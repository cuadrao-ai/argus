"""Validate catalog structure and warn about simple, unmigrated UI literals.

This foundation scan covers direct single-line Swift UI calls. It is not a Swift
parser or a completeness gate. Later call-site slices must extend its coverage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
CATALOG = Path('ios/ArgusFoundation/Resources/Localizable.xcstrings')
REGISTRY = Path('ios/scripts/localization_noncopy.json')
UI_LITERAL = re.compile(
    r'\b(?:Text|Button|Label|TextField|SecureField|Toggle|Picker|NSLocalizedString)'
    r'\(\s*"((?:\\.|[^"\\])*)"'
    r'|\.(?:navigationTitle|accessibilityLabel|accessibilityHint|alert)'
    r'\(\s*"((?:\\.|[^"\\])*)"'
)


def check(root: Path) -> tuple[list[str], list[str]]:
    catalog = json.loads((root / CATALOG).read_text())
    registry = json.loads((root / REGISTRY).read_text())
    errors, warnings = [], []
    if catalog.get('sourceLanguage') != 'es-419':
        errors.append('Catalog sourceLanguage must be es-419')
    strings = catalog.get('strings', {})
    if not strings:
        errors.append('Catalog must contain strings')
    for key, entry in strings.items():
        for language in ('en', 'es-419'):
            unit = entry.get('localizations', {}).get(language, {}).get('stringUnit', {})
            if not isinstance(unit.get('value'), str) or unit.get('state') != 'translated':
                errors.append(f'{key}: missing translated {language} stringUnit')
    allowed = set()
    for entry in registry:
        if not all(isinstance(entry.get(field), str) and entry[field].strip()
                   for field in ('path', 'literal', 'reason')):
            errors.append('Noncopy entries require path, literal and reason')
            continue
        path = Path(entry['path'])
        if path.is_absolute() or '..' in path.parts or not str(path).startswith('ios/'):
            errors.append(f'Noncopy path must stay within ios: {path}')
            continue
        allowed.add((entry['path'], entry['literal']))
    sources = sorted((root / 'ios/ArgusFoundation').rglob('*.swift'))
    sources += sorted((root / 'ios/Packages').glob('*/Sources/**/*.swift'))
    for path in sources:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith('//'):
                continue
            for match in UI_LITERAL.finditer(line):
                literal = next(value for value in match.groups() if value is not None)
                relative = path.relative_to(root).as_posix()
                if literal not in strings and (relative, literal) not in allowed:
                    warnings.append(f'{relative}:{number}: unmigrated UI literal {literal!r}')
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        errors, warnings = check(args.root)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f'ERROR: Cannot read localization inputs: {error}')
        return 1
    for error in errors:
        print(f'ERROR: {error}')
    for warning in warnings:
        print(f'WARNING: {warning}')
    print(f'Localization foundation: {len(errors)} error(s), {len(warnings)} warning(s)')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
