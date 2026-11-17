"""606 workbook labels stay readable without changing their two-digit codes."""

from dataclasses import replace

import pytest
from argus.domain.business.dgii_codes import LABELS, TOOL_LABELS
from argus.domain.business.reporting_file import RecordsExport, build_file
from faker import Faker

from tests.business.test_records_file import FILER, report, row, source, xlsx
from tests.dgii.test_official_606_format import detail, packet
from tests.dgii.test_packet import practice_records

CODE_CHOICES = [(field, code) for field, options in LABELS.items() for code in options]


@pytest.mark.parametrize(("field", "code"), CODE_CHOICES)
def test_tool_label_starts_with_its_two_digit_code(field: str, code: str) -> None:
    assert TOOL_LABELS[field][code][:2] == code


@pytest.mark.parametrize(("field", "code"), CODE_CHOICES)
def test_tool_label_uses_single_spaces(field: str, code: str) -> None:
    label = TOOL_LABELS[field][code]
    assert label.startswith(f"{code} - ")
    assert label == " ".join(label.split())


@pytest.mark.parametrize(("field", "code"), CODE_CHOICES)
def test_workbook_first_two_characters_match_official_606_codes(
    faker: Faker, field: str, code: str
) -> None:
    purchase = practice_records()[0]
    purchase = replace(
        purchase,
        declaration=purchase.declaration.model_copy(update={field: code}),
    )
    official = detail(packet(purchase, FILER, faker.word()))
    projected = row(faker, fiscal_data="complete")
    snapshot = source(
        projected, approved={projected.linked_activity_ids[0]: purchase}
    )
    header, cells = xlsx(
        build_file(snapshot, RecordsExport(report=report(), mode="dgii")).content
    )
    written = {title[1]: cell for title, cell in zip(header, cells, strict=True)}
    for title, expected in (
        ("Tipo Bienes y Servicios Comprados", official[2]),
        ("Forma de Pago", official[22]),
    ):
        kind, label, _ = written[title]
        assert kind == "s"
        assert label[:2] == label.strip()[:2] == expected
