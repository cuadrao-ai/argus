"""Whole-value checks for customer amounts in nested payloads."""

from decimal import Decimal, InvalidOperation


def _assert_no_money_properties(properties: object, amount: str) -> None:
    if isinstance(properties, dict):
        for key, value in properties.items():
            assert key not in {"amount", "amount_minor", "total", "itbis"}
            _assert_no_money_properties(value, amount)
    elif isinstance(properties, list | tuple):
        for value in properties:
            _assert_no_money_properties(value, amount)
    elif isinstance(properties, str | int | float) and not isinstance(properties, bool):
        try:
            value = Decimal(str(properties).replace(",", ""))
        except InvalidOperation:
            return
        assert value != Decimal(amount)
