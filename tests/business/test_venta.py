from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from argus.domain.business.contracts.venta import Customer, MarkVenta, Sale
from argus.domain.business.sales import sales_for_period
from faker import Faker
from pydantic import ValidationError

fake = Faker()


def _digits(length: int) -> str:
    return "1" + fake.numerify("#" * (length - 1))


def _sale(
    *,
    issued_on: date,
    invoice_total: str,
    itbis_charged: str,
    collection_status: str,
) -> Sale:
    now = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    return Sale(
        id=UUID(fake.uuid4()),
        space_id=UUID(fake.uuid4()),
        draft_id=UUID(fake.uuid4()),
        invoice_total=invoice_total,
        itbis_charged=itbis_charged,
        customer=Customer(id_type="rnc", id_number=_digits(9)),
        ncf=f"B{_digits(10)}",
        issued_on=issued_on,
        collection_status=collection_status,
        currency="DOP",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize("ncf", [f"B{_digits(10)}", f"E{_digits(12)}"])
def test_ncf_accepts_the_supported_shapes(ncf: str) -> None:
    request = MarkVenta(
        draft_id=UUID(fake.uuid4()),
        invoice_total="1180.00",
        itbis_charged="180.00",
        customer=Customer(id_type="rnc", id_number=_digits(9)),
        ncf=ncf,
        issued_on=date(2026, 10, 14),
        collection_status="cobrado",
    )

    assert request.ncf == ncf


@pytest.mark.parametrize(
    "ncf",
    [
        "",
        f"A{_digits(10)}",
        f"B{_digits(9)}",
        f"B{_digits(11)}",
        f"E{_digits(11)}",
        f"E{_digits(13)}",
        f"B{_digits(9)}X",
    ],
)
def test_ncf_rejects_every_other_shape(ncf: str) -> None:
    with pytest.raises(ValidationError):
        MarkVenta(
            draft_id=UUID(fake.uuid4()),
            invoice_total="1180.00",
            itbis_charged="180.00",
            customer=Customer(id_type="rnc", id_number=_digits(9)),
            ncf=ncf,
            issued_on=date(2026, 10, 14),
            collection_status="cobrado",
        )


@pytest.mark.parametrize(
    ("id_type", "length"),
    [("rnc", 9), ("cedula", 11)],
)
def test_customer_identity_accepts_only_its_exact_digit_length(
    id_type: str, length: int
) -> None:
    customer = Customer(id_type=id_type, id_number=_digits(length))

    assert customer.id_type == id_type
    with pytest.raises(ValidationError):
        Customer(id_type=id_type, id_number=_digits(11 if length == 9 else 9))


def test_customer_identity_cannot_carry_two_identifiers() -> None:
    with pytest.raises(ValidationError):
        Customer(
            id_type="rnc",
            id_number=_digits(9),
            rnc=_digits(9),
            cedula=_digits(11),
        )


@pytest.mark.parametrize(
    ("invoice_total", "itbis_charged"),
    [("100.00", "100.01"), ("0.00", "0.00")],
)
def test_sale_amounts_reject_itbis_above_total_and_zero_total(
    invoice_total: str, itbis_charged: str
) -> None:
    with pytest.raises(ValidationError):
        MarkVenta(
            draft_id=UUID(fake.uuid4()),
            invoice_total=invoice_total,
            itbis_charged=itbis_charged,
            customer=Customer(id_type="cedula", id_number=_digits(11)),
            ncf=f"E{_digits(12)}",
            issued_on=date(2026, 10, 14),
            collection_status="por_cobrar",
        )


def test_sales_for_period_derives_totals_and_607_rows() -> None:
    charged = _sale(
        issued_on=date(2026, 10, 3),
        invoice_total="1180.00",
        itbis_charged="180.00",
        collection_status="cobrado",
    )
    outstanding = _sale(
        issued_on=date(2026, 10, 14),
        invoice_total="590.00",
        itbis_charged="90.00",
        collection_status="por_cobrar",
    )
    outside = _sale(
        issued_on=date(2026, 9, 30),
        invoice_total="236.00",
        itbis_charged="36.00",
        collection_status="cobrado",
    )

    period = sales_for_period(
        [outside, outstanding, charged],
        start=date(2026, 10, 1),
        end=date(2026, 10, 31),
    )

    assert period.sales == (charged, outstanding)
    assert period.income == Decimal("1500.00")
    assert period.itbis_charged == Decimal("270.00")
    assert period.itbis_cobrado == Decimal("180.00")
    assert period.por_cobrar == Decimal("590.00")
    assert [row.invoiced_amount for row in period.rows] == [
        Decimal("1000.00"),
        Decimal("500.00"),
    ]
    assert period.rows[0].buyer_id_type == 1
    assert all(
        (
            row.modified_ncf,
            row.income_type,
            row.withheld_on,
            row.itbis_withheld,
            row.itbis_perceived,
            row.rent_withheld,
            row.isr_perceived,
            row.selective_tax,
            row.other_tax,
            row.legal_tip,
            row.cash,
            row.transfer,
            row.card,
            row.credit_sale,
            row.gift,
            row.barter,
            row.other_payment,
        )
        == (None,) * 17
        for row in period.rows
    )


def test_customer_identifier_rejects_all_zeros() -> None:
    with pytest.raises(ValidationError):
        Customer(id_type="rnc", id_number="000000000")
    with pytest.raises(ValidationError):
        Customer(id_type="cedula", id_number="00000000000")
