"""The dossier's two calculated 606 amounts are the ones the 606 line writes
for the same record (#2317)."""

from dataclasses import replace

import pytest
from argus.domain.business.contracts.dgii import PurchaseCalculated
from argus.domain.business.contracts.dossier import (
    _UNMEASURED_DOSSIER_FIELDS,
    BusinessDossier,
)
from argus.domain.business.contracts.facts import Unknown
from argus.domain.business.dgii_columns import COLUMNS
from argus.domain.business.dgii_export import line_values
from argus.domain.business.dgii_validation import FiscalRecord, purchase_calculated

from tests.dgii.test_packet import practice_records

RECORDS = practice_records()
PURCHASE = RECORDS[0]
SALE = next(record for record in RECORDS if record.declaration.form == "607")
NAMES = tuple(name for name, _ in COLUMNS["606"])


def _record(overrides: tuple[str, ...] | None = (), **declared: object) -> FiscalRecord:
    return replace(
        PURCHASE,
        declaration=PURCHASE.declaration.model_copy(update=declared),
        fiscal_overrides=overrides,
    )


def _dossier(record: FiscalRecord) -> PurchaseCalculated | None:
    return purchase_calculated(record.facts, record.declaration, record.fiscal_overrides)


@pytest.mark.parametrize(
    ("record", "billed", "advance"),
    [
        pytest.param(_record(itbis=None), "1000.00", "180.00", id="itbis follows the read"),
        pytest.param(
            _record(("itbis",), itbis="150.00"), "1000.00", "150.00", id="itbis overridden"
        ),
        pytest.param(
            _record(itbis=None, itbis_cost="30.00"), "1000.00", "150.00", id="llevado al costo"
        ),
        pytest.param(
            _record(itbis=None, itbis_cost="200.00"), "1000.00", "-20.00", id="costo above itbis"
        ),
        pytest.param(
            _record(itbis=None, services_amount="600.00", goods_amount="400.50"),
            "1000.50",
            "180.00",
            id="servicios and bienes",
        ),
        pytest.param(
            _record(itbis=None, services_amount=None, goods_amount=None),
            "0.00",
            "180.00",
            id="no monto",
        ),
        pytest.param(
            _record(None, itbis=None), "1000.00", "180.00", id="saved before overrides"
        ),
    ],
)
def test_the_dossier_carries_what_the_606_line_writes(
    record: FiscalRecord, billed: str, advance: str
) -> None:
    line = dict(zip(NAMES, line_values(record), strict=True))

    calculated = _dossier(record)

    assert calculated == PurchaseCalculated(billed_amount=billed, itbis_advance=advance)
    assert calculated.billed_amount == line["billed_amount"]
    assert calculated.itbis_advance == line["itbis_advance"]


def test_a_purchase_with_no_itbis_has_no_itbis_por_adelantar() -> None:
    record = _record(("itbis",), itbis=None)

    assert _dossier(record) == PurchaseCalculated(billed_amount="1000.00", itbis_advance=None)
    # The export holds this record by its missing value and writes no line.
    with pytest.raises(TypeError):
        line_values(record)


def test_a_purchase_whose_read_has_no_itbis_has_no_itbis_por_adelantar() -> None:
    facts = PURCHASE.facts.model_copy(
        update={"fiscal": PURCHASE.facts.fiscal.model_copy(update={"itbis": Unknown()})}
    )
    record = replace(_record(itbis=None), facts=facts)

    assert _dossier(record).itbis_advance is None


def test_a_sale_and_a_record_with_no_declaration_calculate_nothing() -> None:
    assert _dossier(SALE) is None
    assert purchase_calculated(PURCHASE.facts, None, ()) is None


def test_the_dossier_field_reaches_people_and_no_model() -> None:
    assert BusinessDossier.model_fields["dgii_calculated"].default is None
    assert _UNMEASURED_DOSSIER_FIELDS["dgii_calculated"] is True
