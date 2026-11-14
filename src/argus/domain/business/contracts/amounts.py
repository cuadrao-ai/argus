from pydantic import Field

from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import Amount, Contract, FactInput, NetAmount


class AmountsPreviewRequest(Contract):
    version: int = Field(ge=1)
    amount: FactInput[Amount] | None = None
    itbis: FactInput[Amount] | None = None
    net_amount: FactInput[Amount] | None = None
    legal_tip: FactInput[Amount] | None = None


class AmountsPreview(Contract):
    net_amount: NetAmount
    mismatch: ReviewFlag | None = None
