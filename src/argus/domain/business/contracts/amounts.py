from pydantic import Field, model_validator

from argus.domain.business.contracts.dgii import DgiiDeclaration
from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import (
    Amount,
    Contract,
    FactInput,
    InheritedValue,
    NetAmount,
)


class AmountsPreviewRequest(Contract):
    version: int = Field(ge=1)
    amount: FactInput[Amount] | None = None
    itbis: FactInput[Amount] | None = None
    net_amount: FactInput[Amount] | None = None
    legal_tip: FactInput[Amount] | None = None
    #: The unsaved fiscal form: its declaration, the linked fields a person
    #: holds apart and the ones they put back, as a review would save them.
    declaration: DgiiDeclaration | None = None
    override_inherited: tuple[str, ...] = ()
    restore_inherited: tuple[str, ...] = ()

    @model_validator(mode="after")
    def one_change_per_link(self) -> "AmountsPreviewRequest":
        if set(self.override_inherited) & set(self.restore_inherited):
            raise ValueError("a field cannot be overridden and restored together")
        return self


class AmountsPreview(Contract):
    net_amount: NetAmount
    mismatch: ReviewFlag | None = None
    #: The links the dossier shows once this draft is saved.
    inheritance: dict[str, InheritedValue]
