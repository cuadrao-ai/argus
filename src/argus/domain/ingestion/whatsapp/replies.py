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
# "captured_reading" approved October 28, 2026: the acknowledgement of a receipt
# read inline right after it carries no link; the follow-up carries it.
_RESEND = (
    "No pudimos guardarlo. Envíalo de nuevo.",
    "We couldn't save it. Please send it again.",
)

REPLIES: dict[str, tuple[str, str]] = {
    "captured": (
        "Recibido. Revísalo aquí: {link}",
        "Received. Review it here: {link}",
    ),
    "captured_reading": (
        "Recibido. Lo estoy leyendo.",
        "Received. I'm reading it.",
    ),
    "read_ready": (
        "Ya leímos tu recibo. Revísalo y confírmalo en Cuadrao: {link}",
        "We read your receipt. Review and confirm it in Cuadrao: {link}",
    ),
    "read_summary": (
        "Leí: {merchant}, {amount} {currency}. Revísalo antes de guardar: {link}",
        "I read: {merchant}, {amount} {currency}. Review it before saving: {link}",
    ),
    "read_attention": (
        "No pudimos leer bien tu recibo. Ábrelo en Cuadrao para completarlo: {link}",
        "We couldn't read your receipt clearly. Open it in Cuadrao to finish it: {link}",
    ),
    "duplicate": (
        "Ya lo teníamos. Revísalo aquí: {link}",
        "We already had this one. Review it here: {link}",
    ),
    "linked": (
        "Listo, este WhatsApp quedó conectado. "
        "Envía aquí la foto o el PDF de tus recibos.",
        "Done, this WhatsApp is connected. Send a photo or PDF of your receipts here.",
    ),
    "whatsapp_link_code_invalid": (
        "Ese código venció o ya se usó. Crea uno nuevo en Cuadrao.",
        "That code has expired or was already used. Create a new one in Cuadrao.",
    ),
    "whatsapp_sender_not_linked": (
        "Este número aún no está vinculado a un negocio en Cuadrao. "
        "Pídele al administrador el código para vincularlo.",
        "This number isn't linked to a business in Cuadrao yet. "
        "Ask the administrator for the code to link it.",
    ),
    "whatsapp_receipt_missing": (
        "Mándame la foto o el PDF del comprobante.",
        "Send me the photo or PDF of the receipt.",
    ),
    "whatsapp_message_unsupported": (
        "Por ahora no podemos recibir audios, stickers ni videos. "
        "Envía la foto o el PDF del recibo.",
        "We can't take voice notes, audio, stickers or videos yet. "
        "Send a photo or PDF of the receipt.",
    ),
    "whatsapp_agent_unavailable": (
        "No pude entender tu mensaje esta vez. Envíalo de nuevo, por favor.",
        "I couldn't process your message this time. Please send it again.",
    ),
    "whatsapp_ai_consent_missing": (
        "Todavía no has dado permiso para que Cuadrao lea tus mensajes con IA. "
        "Puedes activarlo en tu perfil, en App y luego WhatsApp.",
        "You haven't given permission for AI to read your messages yet. "
        "You can turn it on in your profile menu, under App, then WhatsApp.",
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
        "No pudimos leer este archivo. Envíalo como foto o PDF.",
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


def reply_key(
    status: str,
    error_code: str | None,
    *,
    duplicate: bool = False,
    reading: bool = False,
) -> str:
    """Captured and linked answer by status; everything else by its error code."""

    if status == "captured" and duplicate:
        return "duplicate"
    if status == "captured" and reading:
        return "captured_reading"
    key = error_code if status in ("rejected", "failed") and error_code else status
    return _SAME_REPLY.get(key, key)


def inbox_url(app_origin: str) -> str:
    return f"{app_origin.rstrip('/')}/biz"


def review_url(app_origin: str, connection_id: str) -> str:
    return f"{app_origin.rstrip('/')}/biz?receipt={connection_id}"


def compose_reply(
    key: str,
    *,
    language: str | None,
    link: str | None = None,
    limit_mb: int = 10,
    read: dict[str, str] | None = None,
) -> str:
    """One language only: English when the owner's language is en, else Spanish."""

    spanish, english = REPLIES[key]
    body = (english if language == "en" else spanish).format(
        link=link or "", limit_mb=limit_mb, **(read or {})
    )
    # A reply that ends in a link, sent without one, ends as a plain sentence.
    return body if link or not body.endswith(": ") else body[:-2] + "."


def reply_payload(*, to: str, in_reply_to: str | None, body: str) -> dict[str, Any]:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    if in_reply_to is not None:
        payload["context"] = {"message_id": in_reply_to}
    return payload


class ReplyTransport(Protocol):
    async def send(self, payload: dict[str, Any]) -> None: ...


class ReplyFailed(Exception):
    def __init__(self, reason: str, *, outcome_unknown: bool = False) -> None:
        super().__init__(reason)
        self.outcome_unknown = outcome_unknown


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
        except httpx.HTTPError as error:
            raise ReplyFailed(
                "transport",
                outcome_unknown=not isinstance(
                    error, (httpx.ConnectError, httpx.ConnectTimeout)
                ),
            ) from None
        if response.status_code >= 300:
            from argus.domain.ingestion.whatsapp.media import graph_error

            code = graph_error(response).get("code")
            raise ReplyFailed(
                f"{response.status_code}:{code}" if code else str(response.status_code)
            )
