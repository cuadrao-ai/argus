"""Check shipping copy and catalog metadata without building or calling a service."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re

ROOT = Path(__file__).resolve().parents[2]
CATALOG = Path('ios/ArgusFoundation/Resources/Localizable.xcstrings')
EXCEPTIONS = Path('ios/scripts/localization_noncopy.json')
UI = re.compile(r'(?:\b(?:Text|Button|Label|Picker|TextField|SecureField|Toggle|Section|LabeledContent|ProgressView|Link|group|sampleDestination|NSLocalizedString|LocalizedStringKey)|\.(?:navigationTitle|accessibilityLabel|accessibilityHint|accessibilityValue|alert|confirmationDialog|searchable|value))\([^\n]*$|\b(?:title|subtitle|detail|message|placeholder|prompt|annotation|notice|label|text):\s*$')
TECHNICAL = re.compile(r'\b(?:systemImage|systemName|id|addIdentifier|identifier|accessibilityIdentifier|named|forResource|withExtension|format|separator|dateFormat|setLocalizedDateFormatFromTemplate|replacingOccurrences|of|with|contains|hasPrefix|hasSuffix|appendingPathComponent|filename|symbol|image|icon|nameKey|kindKey|errorKey|key):?\s*\(?\s*$')


def string_end(source: str, start: int) -> int:
    delimiter = '"""' if source.startswith('"""', start) else '"'
    index = start + len(delimiter)
    while index < len(source):
        if source.startswith(delimiter, index):
            return index + len(delimiter)
        if source.startswith('\\(', index):
            index = expression_end(source, index + 2) + 1
        elif source[index] == '\\':
            index += 2
        else:
            index += 1
    raise ValueError(f'Unclosed string at {start}')


def expression_end(source: str, index: int) -> int:
    depth = 1
    while index < len(source):
        if source[index] == '"':
            index = string_end(source, index)
            continue
        if source[index] == '(':
            depth += 1
        elif source[index] == ')':
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError('Unclosed interpolation')


def literals(source: str):
    index = 0
    while index < len(source):
        if source.startswith('//', index):
            newline = source.find('\n', index)
            index = len(source) if newline < 0 else newline
        elif source.startswith('/*', index):
            end = source.find('*/', index + 2)
            index = len(source) if end < 0 else end + 2
        elif source[index] == '"':
            end = string_end(source, index)
            yield index, end, source[index:end]
            nested = index + 1
            while nested < end - 1:
                if source.startswith('\\(', nested):
                    finish = expression_end(source, nested + 2)
                    for inner_start, inner_end, raw in literals(source[nested + 2:finish]):
                        yield nested + 2 + inner_start, nested + 2 + inner_end, raw
                    nested = finish + 1
                elif source[nested] == '\\':
                    nested += 2
                else:
                    nested += 1
            index = end
        else:
            index += 1


def identity(path: Path, raw: str) -> str:
    return str(path) + ':' + hashlib.sha256(raw.encode()).hexdigest()[:16]


def static_text(raw: str) -> str:
    value = raw[1:-1]
    index = 0
    result = ''
    while index < len(value):
        if value.startswith('\\(', index):
            index = expression_end(value, index + 2) + 1
        elif value[index] == '\\':
            index += 2
        else:
            result += value[index]
            index += 1
    return result


def context(source: str, start: int) -> str:
    before = source[source.rfind('\n', 0, start) + 1:start]
    return hashlib.sha256(' '.join(before.split()).encode()).hexdigest()[:16]


def copy_candidates(source: str, keys: set[str]):
    for start, end, raw in literals(source):
        before = source[source.rfind('\n', 0, start) + 1:start]
        value = raw[1:-1]
        visible = bool(UI.search(before))
        verbatim = bool(re.search(r'Text\(verbatim:\s*$', before))
        if 'CuadraoCopy.text(' in before and before.rstrip().endswith('CuadraoCopy.text('):
            if value not in keys:
                yield start, end, raw, 'missing catalog key'
            continue
        if value in keys and not verbatim:
            continue
        if not verbatim and (value.endswith('.') or value.startswith('.')) and any(key.startswith(value) or key.endswith(value) for key in keys) and (not re.search(r'(?:Text|Button|Label|LocalizedStringKey|NSLocalizedString)\(\s*$', before) or (source[end:].lstrip().startswith('+') and re.search(r'(?:LocalizedStringKey|NSLocalizedString)\(\s*$', before))):
            continue
        if re.search(r'(?:==|!=)\s*$', before):
            continue
        case_start = source.rfind('case ', 0, start)
        if case_start > source.rfind(':', 0, start) and not re.search(r'[{}]', source[case_start:start]):
            continue
        if re.search(r'value\(forHTTPHeaderField:\s*$', before):
            continue
        static = static_text(raw)
        if not any(character.isalpha() for character in static):
            continue
        if TECHNICAL.search(before) or re.search(r'(?:accessibilityIdentifier|fatalError|precondition|NSLog|ScanTrace\.mark|CaptchaConsoleLog\.write|log\.notice|String\(format:)\([^\n]*$', before):
            continue
        if before.strip().startswith('#Preview('):
            continue
        prefix = value.split('\\(', 1)[0].rstrip()
        if not verbatim and '\\(' in value and any(key.startswith(prefix + ' %') for key in keys):
            continue
        model_label = bool(re.search(r'(?:var|let)\s+\w*(?:title|label|message|detail|notice|caption|placeholder)\w*\s*:', before, re.I))
        declarations = list(re.finditer(r'(?:var|let|func)\s+(\w+)[^\n{]*(?:String|LocalizedStringKey)[^\n{]*\{', source[:start]))
        if declarations and not re.search(r'(?:var|func|struct|enum|class)\s+', source[declarations[-1].end():start]):
            model_label = model_label or bool(re.search(r'title|label|message|detail|notice|caption|placeholder', declarations[-1][1], re.I))

        model_label = model_label or bool(re.search(r'valueTitle:\s*\{[^}]*$', source[max(0, start - 300):start]))
        prose = bool(re.search(r'[A-Za-zÀ-ÿ] [A-Za-zÀ-ÿ]|[áéíóúñÁÉÍÓÚÑ¿¡]', static))
        branding = bool(re.search(r'\bargus\b', static, re.I))
        if visible or model_label or prose or branding:
            yield start, end, raw, 'user-visible Argus branding' if branding else 'uncatalogued UI literal' if visible or model_label else 'uncatalogued prose'


def check(root: Path = ROOT) -> list[str]:
    catalog = json.loads((root / CATALOG).read_text())
    errors = []
    if catalog['sourceLanguage'] != 'es-419':
        errors.append('Catalog source language must be es-419')
    for key, entry in catalog['strings'].items():
        for language in ('es-419', 'en'):
            unit = entry.get('localizations', {}).get(language, {}).get('stringUnit', {})
            if not isinstance(unit.get('value'), str):
                errors.append(f'{key}: missing {language} value')
            elif re.search(r'\bargus\b', unit['value'], re.I):
                errors.append(f'{key}: user-visible Argus branding')
        es = entry.get('localizations', {}).get('es-419', {}).get('stringUnit', {}).get('value', '')
        en = entry.get('localizations', {}).get('en', {}).get('stringUnit', {}).get('value', '')
        if sorted(re.findall(r'%(?:\d+\$)?[@dfgilsu]+', es)) != sorted(re.findall(r'%(?:\d+\$)?[@dfgilsu]+', en)):
            errors.append(f'{key}: interpolation differs between languages')
    exceptions = json.loads((root / EXCEPTIONS).read_text()) if (root / EXCEPTIONS).exists() else {}
    keys = set(catalog['strings'])
    sources = list((root / 'ios/ArgusFoundation').rglob('*.swift'))
    sources += list((root / 'ios/Packages').glob('*/Sources/**/*.swift'))
    for path in sources:
        source = path.read_text()
        for start, _, raw, reason in copy_candidates(source, keys):
            entry = exceptions.get(identity(path.relative_to(root), raw))
            if entry and entry.get('reason') and entry.get('literal') == raw and context(source, start) in entry.get('contexts', []):
                continue
            errors.append(f'{path.relative_to(root)}:{source.count(chr(10), 0, start) + 1}: {reason}: {raw}')
    plist_catalog = json.loads((root / 'ios/ArgusFoundation/Resources/InfoPlist.xcstrings').read_text())
    info = plistlib.loads((root / 'ios/Config/Info.plist').read_bytes())
    for key in ['CFBundleDisplayName'] + [key for key in info if key.startswith('NS') and key.endswith('UsageDescription')]:
        entry = plist_catalog['strings'].get(key, {})
        if not all(language in entry.get('localizations', {}) for language in ('es-419', 'en')):
            errors.append(f'InfoPlist catalog missing {key}')
        elif re.search(r'\bargus\b', json.dumps(entry), re.I):
            errors.append(f'InfoPlist catalog contains user-visible Argus in {key}')
    if info['CFBundleDisplayName'] != 'Cuadrao':
        errors.append('App display name must be Cuadrao')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    arguments = parser.parse_args()
    failures = check(arguments.root)
    for failure in failures:
        print(failure)
    print(f'Localization guard: {len(failures)} failure(s)')
    raise SystemExit(bool(failures))
