import json
from datetime import datetime
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPORT = ROOT / "docs/reports/2026-10-05-cuadrao-privacy-preflight.md"


def main() -> None:
    text = REPORT.read_text()
    checked = 0
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith("https://"):
            continue
        path = target.partition("#")[0]
        assert (REPORT.parent / path).exists(), target
        checked += 1
    for path in Path(__file__).parent.glob("issue-*.json"):
        issue = json.loads(path.read_text())
        assert issue["state"] == "OPEN", path
        assert issue["url"].startswith("https://github.com/lagarcess/argus/issues/"), path
        assert issue["body"], path
        assert issue["number"] == int(path.stem.removeprefix("issue-")), path
        captured = datetime.fromisoformat(issue["captured_at"])
        updated = datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00"))
        assert updated <= captured, path
        assert captured.date().isoformat() == "2026-10-05", path
        checked += 1
    assert checked > 0
    print(f"PASS: {checked} local references and issue snapshots checked")


if __name__ == "__main__":
    main()
