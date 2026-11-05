#!/usr/bin/env python3
"""Check local destinations in changed docs Markdown; policy: docs/ci-docs-checks.md."""

from __future__ import annotations

import argparse
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token


class HTMLLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.destinations: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.destinations.extend(
            value for key, value in attrs if key in {"href", "src"} and value
        )


def destinations(tokens: list[Token]):
    for token in tokens:
        if token.type in {"link_open", "image"}:
            yield token.attrGet("href" if token.type == "link_open" else "src")
        if token.type in {"html_inline", "html_block"}:
            parser = HTMLLinks()
            parser.feed(token.content)
            yield from parser.destinations
        if token.children:
            yield from destinations(token.children)


def check_document(root: Path, document: Path) -> list[str]:
    errors = []
    if not document.resolve().is_relative_to(root):
        return [f"{document.relative_to(root)}: document escapes repository"]
    tokens = MarkdownIt("commonmark").parse(document.read_text(encoding="utf-8"))
    for destination in destinations(tokens):
        parsed = urlsplit(destination)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        path = unquote(parsed.path)
        target = (
            root / path.lstrip("/") if path.startswith("/") else document.parent / path
        ).resolve()
        if not target.is_relative_to(root) or not target.exists():
            errors.append(
                f"{document.relative_to(root)}: invalid local link {destination!r}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="PR base commit or ref")
    args = parser.parse_args()
    root = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
        ).strip()
    ).resolve()
    changed = (
        subprocess.check_output(
            [
                "git",
                "diff",
                "--no-renames",
                "--name-only",
                "-z",
                "--diff-filter=AM",
                f"{args.base}...HEAD",
                "--",
                "docs/",
            ],
            cwd=root,
        )
        .decode()
        .split("\0")
    )
    documents = [
        root / name
        for name in changed
        if name and Path(name).suffix.lower() in {".md", ".markdown"}
    ]
    errors = [error for document in documents for error in check_document(root, document)]
    for error in errors:
        print(error)
    print(f"Checked local links in {len(documents)} changed document(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
