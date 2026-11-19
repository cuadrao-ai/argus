"""Each 606 answer the server suggests names its best source: the receipt
before the last choice for Forma de pago, the last choice before the reader's
pick for Tipo de gasto."""

import pytest
from argus.domain.business.actions.dossier import best_suggestion


@pytest.mark.parametrize(
    ("field", "read", "remembered", "offered"),
    [
        ("payment_method", "03", None, {"value": "03", "source": "receipt"}),
        ("payment_method", "01", "03", {"value": "01", "source": "receipt"}),
        ("payment_method", None, "03", {"value": "03", "source": "last_choice"}),
        ("payment_method", None, None, None),
        ("category", "03", None, {"value": "03", "source": "reading"}),
        ("category", "03", "02", {"value": "02", "source": "last_choice"}),
        ("category", None, "02", {"value": "02", "source": "last_choice"}),
        ("category", None, None, None),
    ],
)
def test_each_answer_takes_its_best_source(field, read, remembered, offered):
    assert best_suggestion(field, read, lambda: remembered) == offered
