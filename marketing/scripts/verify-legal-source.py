import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile


def normalize(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = text.split("\n---\n")[0]
    text = re.sub(r"^(?:#{1,2} |\d+\. |- )", "", text, flags=re.M)
    return " ".join(text.replace("**", "").split())


def document_text(document):
    return " ".join([document["title"], *[
        block.get("text", " ".join(block.get("items", [])))
        for block in document["blocks"]
    ]])


if __name__ == "__main__":
    documents = json.loads((Path(__file__).parents[1] / "content/legal-es.json").read_text())
    with tarfile.open(sys.argv[1]) as archive:
        for slug, document in documents.items():
            source = archive.extractfile(f"cuadrao-legal-pages/marketing/{slug}.md").read().decode()
            expected = normalize(source)
            actual = normalize(document_text(document))
            if actual != expected:
                raise SystemExit(f"FAIL {slug}: published words differ from cleared source")
            print(f"PASS {slug}: {len(expected.split())} words, sha256 {hashlib.sha256(expected.encode()).hexdigest()}")
