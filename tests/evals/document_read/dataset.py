"""The rendered set: every case as a photo with its expected-answer file.

No image is committed. ``python -m tests.evals.document_read.dataset`` writes
the photos and answers under ``temp/`` for a person to look at.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.evals.document_read.cases import (
    Case,
    Expected,
    build_cases,
    coverage,
    expected,
    shapes,
)
from tests.evals.document_read.render import render

DEFAULT_OUT = Path(__file__).resolve().parents[3] / "temp" / "document_read_eval"


@dataclass(frozen=True)
class Sample:
    case: Case
    expected: Expected
    image: bytes

    @property
    def answer_file(self) -> dict[str, object]:
        return {
            "case_id": self.case.case_id,
            "image_sha256": hashlib.sha256(self.image).hexdigest(),
            "shapes": list(shapes(self.case)),
            "expected": asdict(self.expected),
            "dgii_qr_text": self.case.dgii_url,
        }


def build_set() -> tuple[Sample, ...]:
    cases = build_cases()
    with ThreadPoolExecutor() as pool:
        images = list(pool.map(render, cases))
    return tuple(
        Sample(case, expected(case), image)
        for case, image in zip(cases, images, strict=True)
    )


def set_sha256(samples: tuple[Sample, ...]) -> str:
    """One digest of the photos and answers. Two runs with the same digest read the same set."""

    return hashlib.sha256(
        json.dumps([sample.answer_file for sample in samples], sort_keys=True).encode()
    ).hexdigest()


def write_set(samples: tuple[Sample, ...], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        (out / f"{sample.case.case_id}.jpg").write_bytes(sample.image)
        (out / f"{sample.case.case_id}.expected.json").write_text(
            json.dumps(sample.answer_file, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def coverage_table(samples: tuple[Sample, ...]) -> str:
    rows = coverage(tuple(sample.case for sample in samples)).items()
    return "\n".join(
        ["| Shape | Receipts |", "| --- | ---: |"]
        + [f"| {shape} | {count} |" for shape, count in rows]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    samples = build_set()
    write_set(samples, args.out)
    print(f"{len(samples)} receipts in {args.out}  set_sha256={set_sha256(samples)}")
    print(coverage_table(samples))


if __name__ == "__main__":
    main()
