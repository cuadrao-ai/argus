#!/usr/bin/env python3
"""Fails when any app source puts a Done (or any) control above the keyboard.

On iOS 26 a keyboard toolbar item or an input accessory view floats as a blue pill over the sheet's own button.
Keyboards close by tapping away (KeyboardTapAway), scrolling or the Return key, never by a Done control.
The whole file is searched, so a placement argument split across lines or spelled out in full is still caught."""
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parents[1] / "ArgusFoundation"
banned = [
    (re.compile(r"placement:\s*(?:ToolbarItemPlacement)?\.keyboard\b"), "toolbar placement .keyboard"),
    (re.compile(r"ToolbarItemPlacement\s*=\s*\.keyboard\b"), "a ToolbarItemPlacement set to .keyboard"),
    (re.compile(r"\binputAccessoryView(?:Controller)?\b"), "inputAccessoryView"),
    (re.compile(r"\bUIToolbar\b"), "UIToolbar"),
]
found = []
for path in sorted(root.rglob("*.swift")):
    text = path.read_text()
    for pattern, name in banned:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append(f"{path.relative_to(root.parent)}:{line}: {name}")
if found:
    print("Controls above the keyboard are not allowed:\n" + "\n".join(found))
    sys.exit(1)
print("No controls above the keyboard.")
