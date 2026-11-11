"""The 606 expense and payment codes with their API and workbook labels."""

from typing import NamedTuple


class _Choice(NamedTuple):
    label: str
    tool_label: str


# The workbook labels are the exact choices in the DGII Formato 606 v2020.2.
# Sheet "Herramienta Formato 606": category AD2:AD12, payment AF2:AF8.
# Its validation lists use inconsistent spacing, including trailing spaces.
_CHOICES = {
    "category": {
        "01": _Choice("Gastos de personal", "01-GASTOS DE PERSONAL "),
        "02": _Choice(
            "Gastos por trabajos, suministros y servicios",
            "02-GASTOS POR TRABAJOS, SUMINISTROS Y SERVICIOS ",
        ),
        "03": _Choice("Arrendamientos", "03-ARRENDAMIENTOS "),
        "04": _Choice("Gastos de activos fijo", "04-GASTOS DE ACTIVOS FIJO "),
        "05": _Choice("Gastos de representación", "05 -GASTOS DE REPRESENTACIÓN "),
        "06": _Choice("Otras deducciones admitidas", "06 -OTRAS DEDUCCIONES ADMITIDAS "),
        "07": _Choice("Gastos financieros", "07 -GASTOS FINANCIEROS "),
        "08": _Choice("Gastos extraordinarios", "08 -GASTOS EXTRAORDINARIOS "),
        "09": _Choice(
            "Compras y gastos que formarán parte del costo de venta",
            "09 -COMPRAS Y GASTOS QUE FORMARAN PARTE DEL COSTO DE VENTA ",
        ),
        "10": _Choice("Adquisiciones de activos", "10 -ADQUISICIONES DE ACTIVOS "),
        "11": _Choice("Gastos de seguros", "11- GASTOS DE SEGUROS"),
    },
    "payment_method": {
        "01": _Choice("Efectivo", "01 - EFECTIVO"),
        "02": _Choice(
            "Cheques/transferencias/depósito", "02 - CHEQUES/TRANSFERENCIAS/DEPÓSITO"
        ),
        "03": _Choice("Tarjeta crédito/débito", "03 - TARJETA CRÉDITO/DÉBITO"),
        "04": _Choice("Compra a crédito", "04 - COMPRA A CREDITO"),
        "05": _Choice("Permuta", "05 -\u00a0 PERMUTA"),
        "06": _Choice("Nota de crédito", "06 - NOTA DE CREDITO"),
        "07": _Choice("Mixto", "07 - MIXTO"),
    },
}

LABELS = {
    field: {code: choice.label for code, choice in options.items()}
    for field, options in _CHOICES.items()
}
TOOL_LABELS = {
    field: {code: choice.tool_label for code, choice in options.items()}
    for field, options in _CHOICES.items()
}
EXPENSE_TYPES = LABELS["category"]
PAYMENT_FORMS = LABELS["payment_method"]

#: The payment form a Business account implies when the person chose none:
#: cash 01, bank 02, card 03. Owner funds and any other account imply none.
PAYMENT_FORM_BY_ACCOUNT_TYPE = {
    "cash": "01",
    "checking": "02",
    "savings": "02",
    "credit_card": "03",
}
