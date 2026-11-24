"""José's two 606 lists have one owner: the code tables in ``dgii_codes``. The
typed declaration accepts exactly those codes, the fields route serves their
labels beside the codes, and the approval derives a payment form from them."""

from typing import get_args

from argus.domain.business.contracts.dgii import ExpenseType, PaymentForm
from argus.domain.business.dgii_codes import (
    EXPENSE_TYPES,
    PAYMENT_FORM_BY_ACCOUNT_TYPE,
    PAYMENT_FORMS,
)
from argus.domain.business.dgii_form import input_fields


def test_the_declaration_accepts_exactly_the_listed_codes():
    assert get_args(ExpenseType) == tuple(EXPENSE_TYPES)
    assert get_args(PaymentForm) == tuple(PAYMENT_FORMS)


def test_expense_types_are_the_dgii_list_in_order():
    assert EXPENSE_TYPES == {
        "01": "Gastos de personal",
        "02": "Gastos por trabajos, suministros y servicios",
        "03": "Arrendamientos",
        "04": "Gastos de activos fijo",
        "05": "Gastos de representación",
        "06": "Otras deducciones admitidas",
        "07": "Gastos financieros",
        "08": "Gastos extraordinarios",
        "09": "Compras y gastos que formarán parte del costo de venta",
        "10": "Adquisiciones de activos",
        "11": "Gastos de seguros",
    }


def test_payment_forms_are_the_dgii_list_in_order():
    assert PAYMENT_FORMS == {
        "01": "Efectivo",
        "02": "Cheques/transferencias/depósito",
        "03": "Tarjeta crédito/débito",
        "04": "Compra a crédito",
        "05": "Permuta",
        "06": "Nota de crédito",
        "07": "Mixto",
    }


def test_an_account_implies_only_a_listed_payment_form():
    assert set(PAYMENT_FORM_BY_ACCOUNT_TYPE.values()) <= set(PAYMENT_FORMS)
    assert PAYMENT_FORM_BY_ACCOUNT_TYPE == {
        "cash": "01",
        "checking": "02",
        "savings": "02",
        "credit_card": "03",
    }


def test_the_fields_route_serves_labels_beside_the_codes():
    fields = {field["name"]: field for field in input_fields("606")}
    assert fields["category"]["options"] == list(EXPENSE_TYPES)
    assert fields["category"]["labels"] == EXPENSE_TYPES
    assert fields["payment_method"]["options"] == list(PAYMENT_FORMS)
    assert fields["payment_method"]["labels"] == PAYMENT_FORMS
    assert fields["id_type"]["labels"] == {}
    assert all(field["labels"] == {} for field in input_fields("607"))
