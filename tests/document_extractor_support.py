"""Local preparation and request admission for extractor stand-ins."""

from collections.abc import Awaitable, Callable
from typing import Any

from argus.domain.ingestion.documents.preparation import PreparedDocument
from argus.llm.provider_permit import ProviderAdmissionError


class StubPreparation:
    def prepare(
        self, content: bytes, media_type: str, *, rebuilt_image: bytes | None = None
    ) -> PreparedDocument:
        return PreparedDocument(1, (rebuilt_image,) if rebuilt_image else ())


async def admit(before_request: Callable[[], Awaitable[None]] | None) -> None:
    if before_request is not None:
        try:
            await before_request()
        except Exception as error:
            raise ProviderAdmissionError(error) from None


async def start_request(options: dict[str, Any]) -> None:
    if before_request := options.pop("before_request", None):
        await before_request()
