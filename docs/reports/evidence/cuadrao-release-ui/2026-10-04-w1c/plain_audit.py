"""Prints every plain-style Button/NavigationLink statement that has no contentShape, for review."""
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
start = re.compile(r"\b(Button|NavigationLink)\b")
skip = ("/Invitations/", "/Household/")
for path in sorted(root.rglob("*.swift")):
    if any(part in str(path) for part in skip): continue
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if "buttonStyle(.plain)" not in line: continue
        j = i
        while j > 0 and i - j < 25 and not start.search(lines[j]): j -= 1
        window = "\n".join(lines[j:i + 1])
        if "contentShape" in window: continue
        print(f"== {path}:{j + 1}-{i + 1}")
        for text in lines[j:i + 1]: print("   " + text.strip()[:170])
