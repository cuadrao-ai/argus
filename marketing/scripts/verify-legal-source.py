import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile


def normalize(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"^(?:#{1,2} |\d+\. |- )", "", text, flags=re.M)
    return " ".join(text.replace("**", "").split())


def document_text(document):
    return " ".join([document["title"], *[
        block.get("text", " ".join(block.get("items", [])))
        for block in document["blocks"]
    ]])


if __name__ == "__main__":
    marketing = Path(__file__).parents[1]
    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else marketing / "content/legal-waitlist-source"
    for locale, index in (("es", 0), ("en", 1)):
        documents = json.loads((marketing / f"content/legal-{locale}.json").read_text())
        for slug, document in documents.items():
            if source_path.is_dir():
                source = (source_path / f"{slug}.md").read_text()
            else:
                with tarfile.open(source_path) as archive:
                    source = archive.extractfile(f"cuadrao-legal-pages/marketing/{slug}.md").read().decode()
            expected = normalize(source.split("\n---\n")[index])
            actual = normalize(document_text(document))
            if actual != expected:
                raise SystemExit(f"FAIL {locale}/{slug}: published words differ from cleared source")
            print(f"PASS {locale}/{slug}: {len(expected.split())} words, sha256 {hashlib.sha256(expected.encode()).hexdigest()}")
