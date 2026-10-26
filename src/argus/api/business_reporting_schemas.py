"""Transport commands share the domain's fixed query and private recipe contract."""

from pydantic import Field

from argus.domain.business.reporting_preferences import ReportInput
from argus.domain.business.reporting_query import Contract, ReportRequest


class ExportReport(Contract):
    report: ReportInput = ReportRequest()
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeleteReportView(Contract):
    expected_version: int = Field(ge=1, strict=True)
