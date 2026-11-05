from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.domain.recording.currency import parse_minor_units
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.money_schemas import MoneyRequest


class TransferSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CUADRAO_", extra="ignore")
    cross_currency_transfers_enabled: bool = False


@dataclass(frozen=True)
class TransferAmounts:
    source_minor: int
    destination_minor: int


def transfer_amounts(
    request: MoneyRequest, source_currency: str, destination_currency: str
) -> TransferAmounts:
    mixed = source_currency != destination_currency
    if mixed and not TransferSettings().cross_currency_transfers_enabled:
        raise RecordingInputError(
            "cross_currency_transfers_disabled",
            "Transfers between different currencies are not available yet.",
        )
    source = parse_minor_units(request.amount, source_currency)
    if mixed and request.destination_amount is None:
        raise RecordingInputError(
            "destination_amount_required",
            "Enter the actual amount received in the destination account.",
        )
    destination = (
        parse_minor_units(request.destination_amount, destination_currency)
        if request.destination_amount is not None
        else source
    )
    if source <= 0 or destination <= 0:
        raise RecordingInputError(
            "amount_positive_required", "Enter positive amounts for both accounts."
        )
    if not mixed and source != destination:
        raise RecordingInputError(
            "transfer_amount_mismatch",
            "Use equal amounts for a transfer in one currency.",
        )
    return TransferAmounts(source, destination)
