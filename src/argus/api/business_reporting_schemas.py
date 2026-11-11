"""Transport commands share the domain's fixed query and private recipe contract."""

from pydantic import Field

from argus.domain.business.reporting_query import Contract


class DeleteReportView(Contract):
    expected_version: int = Field(ge=1, strict=True)
