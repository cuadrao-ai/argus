"""Compare the catalog with the Spanish the pre-catalog base shipped inline."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import tempfile

import localization_guard as guard

# Last codex/private-alpha-next commit whose copy lived in `spanish ? "es" : "en"` literals.
BASE = '43dfdd036628d99ef51f113e507bc12a332c2663'
STRINGS = 'ios/ArgusFoundation/Resources/{language}.lproj/Localizable.strings'
CONDITION = re.compile(r'(?<![\w.!])(?:[\w.]+\.)?(?:spanish|es)\s*\?(?![?.])')
IF_RETURN = re.compile(r'if (?:spanish|es) \{\s*return ([^\n]*?) \}\n\s*return ([^\n]*)\n')
TEXT_HELPER = re.compile(r'(?<![\w.])text\(\s*(?=")')
LABELED = re.compile(r'\bspanish:\s*(?=")')
STRINGS_LINE = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)";', re.M)
ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', '0': '\0', '"': '"', "'": "'", '\\': '\\'}


class BaseUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Pair:
    file: str
    es: str
    en: str


@dataclass(frozen=True)
class Base:
    pairs: list[Pair]
    literals: dict[str, set[str]]
    tables: dict[str, dict[str, str]]


@dataclass(frozen=True)
class Finding:
    kind: str
    key: str
    es: str
    en: str
    base_es: str | None
    file: str | None


def branch_end(source: str, index: int, stop: str) -> int:
    depth = ternaries = 0
    while index < len(source):
        character = source[index]
        if character == '"':
            index = guard.string_end(source, index)
            continue
        if character in '([{':
            depth += 1
        elif character in ')]}':
            if depth == 0:
                return index
            depth -= 1
        elif depth == 0:
            if character == '?' and source[index - 1] != '?' and source[index + 1] not in '?.':
                ternaries += 1
            elif character == ':':
                if ternaries == 0:
                    return index
                ternaries -= 1
            elif character in stop:
                return index
        index += 1
    return index


def top_level_literals(fragment: str) -> list[str]:
    found: list[tuple[int, int, str]] = []
    for start, end, raw in guard.literals(fragment):
        if not any(outer_start <= start and end <= outer_end for outer_start, outer_end, _ in found):
            found.append((start, end, raw))
    return [raw for _, _, raw in found]


def unescape(body: str, printf: bool = False) -> tuple[str, list[str]]:
    """Text for a Swift literal body, with each `\\(expression)` as a `\\0` placeholder.

    A literal `%` becomes `%%` unless the body already uses printf escaping.
    """
    text = ''
    expressions: list[str] = []
    index = 0
    while index < len(body):
        if body.startswith('\\(', index):
            end = guard.expression_end(body, index + 2)
            expressions.append(body[index + 2:end])
            text += '\0'
            index = end + 1
        elif body.startswith('\\u{', index):
            end = body.index('}', index)
            text += chr(int(body[index + 3:end], 16))
            index = end + 1
        elif body[index] == '\\':
            text += ESCAPES.get(body[index + 1], body[index + 1])
            index += 2
        else:
            text += '%%' if body[index] == '%' and not printf else body[index]
            index += 1
    return text, expressions


def catalog_value(raw: str, order: list[str] | None = None) -> tuple[str, list[str]] | None:
    """Positional `%N$@` numbering follows the English expression order when `order` is given.

    Returns None when the interpolation counts differ, since no one catalog key holds both.
    """
    text, expressions = unescape(raw[1:-1])
    if order is not None and len(order) != len(expressions):
        return None
    positions = list(range(len(expressions)))
    if order is not None:
        unmatched = [index for index, expression in enumerate(order) if expression not in expressions]
        positions = [order.index(expression) if expression in order else unmatched.pop(0) for expression in expressions]
    for position in positions:
        text = text.replace('\0', f'%{position + 1}$@', 1)
    return text, expressions


def branches(source: str) -> list[tuple[str, str]]:
    """(Spanish, English) source fragments for every inline pair form the base used."""
    found = []
    for match in CONDITION.finditer(source):
        start = match.end()
        middle = branch_end(source, start, '')
        if middle < len(source) and source[middle] == ':':
            end = branch_end(source, middle + 1, ',\n')
            found.append((source[start:middle], source[middle + 1:end]))
    found += [(match[1], match[2]) for match in IF_RETURN.finditer(source)]
    for pattern in (TEXT_HELPER, LABELED):
        for match in pattern.finditer(source):
            spanish_end = guard.string_end(source, match.end())
            rest = re.match(r'\s*,\s*(?:english:\s*)?(?=")', source[spanish_end:])
            if rest:
                english_start = spanish_end + rest.end()
                found.append((source[match.end():spanish_end], source[english_start:guard.string_end(source, english_start)]))
    return found


def nested_literals(raw: str) -> list[str]:
    """Top-level literals inside the `\\(expressions)` of one literal."""
    body = raw[1:-1]
    found = []
    index = 0
    while index < len(body):
        if body.startswith('\\(', index):
            end = guard.expression_end(body, index + 2)
            found += top_level_literals(body[index + 2:end])
            index = end + 1
        elif body[index] == '\\':
            index += 2
        else:
            index += 1
    return found


def pair_literals(file: str, es_raw: str, en_raw: str) -> list[Pair]:
    if es_raw.startswith('"""') or en_raw.startswith('"""'):
        return []
    en, order = catalog_value(en_raw)
    spanish = catalog_value(es_raw, order)
    if spanish is None:
        return []
    found = [Pair(file, spanish[0], en)]
    nested_es, nested_en = nested_literals(es_raw), nested_literals(en_raw)
    if len(nested_es) == len(nested_en):
        for inner_es, inner_en in zip(nested_es, nested_en):
            found += pair_literals(file, inner_es, inner_en)
    return found


def pairs(file: str, source: str) -> list[Pair]:
    found = []
    for spanish, english in branches(source):
        es_literals, en_literals = top_level_literals(spanish), top_level_literals(english)
        if len(es_literals) == len(en_literals):
            for es_raw, en_raw in zip(es_literals, en_literals):
                found += pair_literals(file, es_raw, en_raw)
    return found


def strings_table(text: str) -> dict[str, str]:
    return {unescape(key, printf=True)[0]: unescape(value, printf=True)[0] for key, value in STRINGS_LINE.findall(text)}


def load_base(repo: Path, revision: str = BASE) -> Base:
    if subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', revision + '^{commit}'], capture_output=True).returncode:
        raise BaseUnavailable(f'commit {revision} is not in this clone')
    with tempfile.TemporaryDirectory() as directory:
        archive = subprocess.run(['git', '-C', str(repo), 'archive', revision, 'ios/ArgusFoundation', 'ios/Packages'], capture_output=True, check=True).stdout
        subprocess.run(['tar', '-x', '-C', directory], input=archive, check=True)
        root = Path(directory)
        found: list[Pair] = []
        literals: dict[str, set[str]] = {}
        sources = list((root / 'ios/ArgusFoundation').rglob('*.swift')) + list((root / 'ios/Packages').glob('*/Sources/**/*.swift'))
        for path in sorted(sources):
            file, source = str(path.relative_to(root)), path.read_text()
            found += pairs(file, source)
            literals[file] = {catalog_value(raw)[0] for _, _, raw in guard.literals(source) if not raw.startswith('"""')}
        tables = {language: strings_table((root / STRINGS.format(language=language)).read_text()) for language in ('es-419', 'en')}
    return Base(found, literals, tables)


def compare(catalog: dict, base: Base) -> list[Finding]:
    by_en: dict[str, list[Pair]] = {}
    for pair in base.pairs:
        by_en.setdefault(pair.en, []).append(pair)
    everywhere = set().union(*base.literals.values())
    findings = []
    for key, entry in catalog['strings'].items():
        es = entry['localizations']['es-419']['stringUnit']['value']
        en = entry['localizations']['en']['stringUnit']['value']
        if not key.startswith('copy.'):
            base_es, base_en = base.tables['es-419'].get(key), base.tables['en'].get(key)
            if base_es is None:
                kind = 'todo' if es == en else 'spanish added'
            elif es == base_es or base_es == base_en:
                kind = 'same'
            else:
                kind = 'replaced' if es == en else 'changed'
            findings.append(Finding(renamed(kind, es, base_es, set()), key, es, en, base_es, STRINGS.format(language='es-419')))
            continue
        stem = key.split('.')[1]
        files = [file for file in base.literals if file in entry.get('comment', '')]
        files = files or [file for file in base.literals if Path(file).stem[:1].lower() + Path(file).stem[1:] == stem]
        own = [pair for pair in by_en.get(en, []) if pair.file in files]
        spanish_values = {pair.es for pair in own}
        if es in spanish_values:
            kind, base_es, file = 'same', es, own[0].file
        elif own:
            file = ', '.join(sorted({pair.file for pair in own}))
            base_es = spanish_values.pop() if len(spanish_values) == 1 else None
            kind = 'ambiguous' if base_es is None else 'replaced' if es == en else 'same' if es in everywhere else 'changed'
        elif any(en in base.literals[file] for file in files):
            base_es, file = None, files[0]
            kind = 'todo' if es == en else 'same' if es in everywhere else 'spanish added'
        else:
            candidates = {pair.es for pair in by_en.get(en, [])}
            base_es = file = None
            if es == en:
                kind = 'todo' if not candidates else 'ambiguous' if len(candidates) > 1 else 'replaced'
                if kind == 'replaced':
                    base_es, file = by_en[en][0].es, by_en[en][0].file
                elif kind == 'ambiguous':
                    file = ', '.join(sorted({pair.file for pair in by_en[en]}))
            else:
                kind = 'same' if es in everywhere and en in everywhere else 'english added' if es in everywhere else 'spanish added'
        findings.append(Finding(renamed(kind, es, base_es, everywhere), key, es, en, base_es, file))
    return findings


def renamed(kind: str, es: str, base_es: str | None, everywhere: set[str]) -> str:
    """'renamed' when the only Spanish difference from the base is the Argus to Cuadrao rename."""
    if kind not in ('changed', 'spanish added'):
        return kind
    if base_es is not None:
        return 'renamed' if base_es.replace('Argus', 'Cuadrao') == es else kind
    return 'renamed' if 'Cuadrao' in es and es.replace('Cuadrao', 'Argus') in everywhere else kind


def restore(catalog: dict, findings: list[Finding], revision: str = BASE) -> int:
    """Write the base Spanish back for every replaced key and drop TODO-COPY where the base already had the text."""
    touched = 0
    for finding in findings:
        entry = catalog['strings'][finding.key]
        pending = 'TODO-COPY' in entry.get('comment', '')
        if finding.kind == 'replaced':
            entry['localizations']['es-419']['stringUnit']['value'] = finding.base_es
        elif finding.kind != 'same' or not pending:
            continue
        entry['comment'] = f'Existing copy at {revision} in {finding.file}'
        touched += 1
    return touched


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=guard.ROOT)
    parser.add_argument('--base', default=BASE)
    parser.add_argument('--fix', action='store_true', help='write the base Spanish back for every replaced key')
    parser.add_argument('--show', default='replaced,changed,renamed,english added,spanish added,ambiguous', help='comma-separated kinds to list')
    arguments = parser.parse_args()
    path = arguments.root / guard.CATALOG
    catalog = json.loads(path.read_text())
    findings = compare(catalog, load_base(arguments.root, arguments.base))
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
    for finding in findings:
        if finding.kind in arguments.show.split(','):
            print(f'{finding.kind}\t{finding.key}\t{finding.en!r}\tes={finding.es!r}\tbase={finding.base_es!r}\t{finding.file}')
    print('Base copy:', ', '.join(f'{kind} {count}' for kind, count in sorted(counts.items())))
    if arguments.fix:
        restored = restore(catalog, findings, arguments.base)
        path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')
        print(f'Restored {restored} key(s) from {arguments.base}')
    raise SystemExit(bool(counts.get('replaced')) and not arguments.fix)
