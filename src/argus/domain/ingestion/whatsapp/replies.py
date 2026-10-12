"""Acknowledgement replies: pure composition, sending behind a transport.

Replies are free-form text sent as an answer to the person's own message, so
they always fall inside WhatsApp's 24-hour customer service window. Nothing
here starts a conversation; that would need an approved template, so intake
never sends outside the window.

A reply uses one language: the sender link's ``reply_language``, the web app's
language when the owner asked for the link code. A sender with no active link
gets Spanish.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from argus.domain.ingestion.whatsapp.media import GRAPH_HOST
from argus.domain.ingestion.whatsapp.store import SENDER_LINK_REVOKED

# Founder-approved copy, October 8, 2026 (docs/specs/lanes/cuadrao-whatsapp-intake.md).
_RESEND = (
    "No pudimos guardar el recibo. Envíalo de nuevo.",
    "We couldn't save the receipt. Please send it again.",
)

REPLIES: dict[str, tuple[str, str]] = {
    "captured": (
        "Recibimos tu recibo y lo guardamos en tu bandeja. "
        "Revísalo y confírmalo en Cuadrao: {link}",
        "We got your receipt and saved it to your inbox. "
        "Review and confirm it in Cuadrao: {link}",
    ),
    "duplicate": (
        "Ya tenemos este recibo en tu bandeja, así que no lo guardamos dos veces. "
        "Revísalo en Cuadrao: {link}",
        "This receipt is already in your inbox, so we didn't save it twice. "
        "Review it in Cuadrao: {link}",
    ),
    "linked": (
        "Listo. Este WhatsApp quedó conectado a tu negocio en Cuadrao. "
        "Envía aquí la foto o el PDF de un recibo.",
        "Done. This WhatsApp is now connected to your business in Cuadrao. "
        "Send a photo or PDF of a receipt here.",
    ),
    "whatsapp_link_code_invalid": (
        "Ese código venció o ya se usó. Crea uno nuevo en Cuadrao.",
        "That code has expired or was already used. Create a new one in Cuadrao.",
    ),
    "whatsapp_sender_not_linked": (
        "Este número no está conectado a Cuadrao. "
        "Conéctalo desde Cuadrao en la web y vuelve a enviar el recibo.",
        "This number isn't connected to Cuadrao. "
        "Connect it from Cuadrao on the web, then send the receipt again.",
    ),
    "whatsapp_receipt_missing": (
        "Por aquí solo recibimos recibos. Envía la foto o el PDF del recibo.",
        "We only take receipts here. Send a photo or PDF of the receipt.",
    ),
    "whatsapp_media_unsupported": (
        "Solo podemos recibir fotos JPG o PNG y archivos PDF.",
        "We can only take JPG or PNG photos and PDF files.",
    ),
    "whatsapp_media_too_large": (
        "El archivo pesa más de {limit_mb} MB. Envía una foto o un PDF más pequeño.",
        "The file is larger than {limit_mb} MB. Send a smaller photo or PDF.",
    ),
    "whatsapp_media_invalid": (
        "No pudimos abrir ese archivo. Envía otra foto o PDF del recibo.",
        "We couldn't open that file. Send another photo or PDF of the receipt.",
    ),
    "whatsapp_media_expired": _RESEND,
    "whatsapp_media_unavailable": _RESEND,
    "whatsapp_capture_failed": _RESEND,
}


_SAME_REPLY = {
    "whatsapp_media_untrusted": "whatsapp_media_unavailable",
    "whatsapp_processing_failed": "whatsapp_capture_failed",
    # The link ended while the receipt was in flight: answer as for any
    # number that is not linked.
    SENDER_LINK_REVOKED: "whatsapp_sender_not_linked",
}


def reply_key(status: str, error_code: str | None, *, duplicate: bool = False) -> str:
    """Captured and linked answer by status; everything else by its error code."""

    if status == "captured" and duplicate:
        return "duplicate"
    key = error_code if status in ("rejected", "failed") and error_code else status
    return _SAME_REPLY.get(key, key)


def review_url(app_origin: str, connection_id: str) -> str:
    return f"{app_origin.rstrip('/')}/biz?receipt={connection_id}"


def compose_reply(
    key: str,
    *,
    language: str | None,
    link: str | None = None,
    limit_mb: int = 10,
) -> str:
    """One language only: English when the owner's language is en, else Spanish."""

    spanish, english = REPLIES[key]
    return (english if language == "en" else spanish).format(
        link=link or "", limit_mb=limit_mb
    )


def reply_payload(*, to: str, in_reply_to: str, body: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "context": {"message_id": in_reply_to},
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }


class ReplyTransport(Protocol):
    async def send(self, payload: dict[str, Any]) -> None: ...


class ReplyFailed(Exception):
    pass


class CloudApiTransport:
    """``POST /{phone-number-id}/messages``; only built when outbound is enabled."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        access_token: str,
        phone_number_id: str,
        graph_api_version: str,
    ) -> None:
        self._client = client
        self._url = f"https://{GRAPH_HOST}/{graph_api_version}/{phone_number_id}/messages"
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def send(self, payload: dict[str, Any]) -> None:
        try:
            response = await self._client.post(
                self._url, json=payload, headers=self._headers, timeout=10.0
            )
        except httpx.HTTPError:
            raise ReplyFailed("transport") from None
        if response.status_code >= 300:
            raise ReplyFailed(str(response.status_code))
