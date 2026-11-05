"""Independent authored transactions for testing provisional harness mechanics."""

import csv
from collections.abc import Callable
from pathlib import Path

import pytest
from faker import Faker


@pytest.fixture
def valid_row() -> dict[str, str]:
    fake = Faker("es")
    fake.seed_instance(411)
    return {
        "source_id": "independent-source-1",
        "date": "2026-09-14",
        "description": fake.company(),
        "amount": "125.50",
        "currency": "DOP",
        "kind": "expense",
        "account": "SYNTHETIC-CASH",
        "destination": "personal",
    }


@pytest.fixture
def csv_factory(tmp_path: Path) -> Callable:
    def write(rows: list[dict[str, str]], name: str = "independent.csv") -> Path:
        path = tmp_path / name
        headers = list(dict.fromkeys(key for row in rows for key in row))
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        return path

    return write
