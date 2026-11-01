"""The two 606 lists a person picks from, NG 07-2018: Tipo de Bienes y
Servicios Comprados and Forma de Pago, code to label. The typed declaration's
Literals, the fields route and the approval's account derivation all read
these tables and nothing else names a code or a label."""

EXPENSE_TYPES = {
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

PAYMENT_FORMS = {
    "01": "Efectivo",
    "02": "Cheques/transferencias/depósito",
    "03": "Tarjeta crédito/débito",
    "04": "Compra a crédito",
    "05": "Permuta",
    "06": "Nota de crédito",
    "07": "Mixto",
}

#: The payment form a Business account implies when the person chose none:
#: cash 01, bank 02, card 03. Owner funds and any other account imply none.
PAYMENT_FORM_BY_ACCOUNT_TYPE = {
    "cash": "01",
    "checking": "02",
    "savings": "02",
    "credit_card": "03",
}

#: The declaration fields whose codes carry a label, by field name.
LABELS = {"category": EXPENSE_TYPES, "payment_method": PAYMENT_FORMS}
