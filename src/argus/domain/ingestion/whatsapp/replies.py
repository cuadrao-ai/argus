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

# Iris's approved WhatsApp copy (2026-11-27). Each pair is Spanish, English.
REPLIES: dict[str, tuple[str, str]] = {
    "batch_received": (
        "Recibimos {n} facturas, gracias.",
        "We received {n} invoices, thank you.",
    ),
    "batch_received_one": (
        "Recibimos tu factura, gracias.",
        "We received your invoice, thank you.",
    ),
    "batch_in_inbox": ("Ya están en la Bandeja:", "They're in your Inbox:"),
    "batch_in_inbox_one": ("Ya está en la Bandeja:", "It's in your Inbox:"),
    "batch_business_line": ("• {business}: {n}", "• {business}: {n}"),
    "batch_more_businesses": (
        "y {k} negocios más: {n} facturas",
        "and {k} more businesses: {n} invoices",
    ),
    "batch_more_businesses_one": (
        "y 1 negocio más: {n} facturas",
        "and 1 more business: {n} invoices",
    ),
    "batch_held": (
        "{n} quedaron sin negocio. Te esperan en Cuadrao.",
        "{n} have no business yet. They're waiting for you in Cuadrao.",
    ),
    "batch_held_one": (
        "1 quedó sin negocio. Te espera en Cuadrao.",
        "1 has no business yet. It's waiting for you in Cuadrao.",
    ),
    "batch_duplicates": ("{n} ya las teníamos.", "We already had {n}."),
    "batch_duplicates_one": ("1 ya la teníamos.", "We already had 1."),
    "batch_reading_follow": (
        "Las demás se están leyendo. Puedes seguirlas en Cuadrao.",
        "The rest are still being read. You can follow them in Cuadrao.",
    ),
    "batch_reading_follow_one": (
        "La otra se está leyendo. Puedes seguirla en Cuadrao.",
        "The other one is still being read. You can follow it in Cuadrao.",
    ),
    "batch_read_tomorrow": (
        "Hoy llegamos al límite de lecturas. {n} se leerán mañana y no hace falta enviarlas de nuevo.",
        "We reached today's reading limit. {n} will be read tomorrow, and you don't need to send them again.",
    ),
    "duplicate": (
        "Esta ya la teníamos, gracias. No se guardó dos veces.",
        "We already had this one, thank you. It wasn't saved twice.",
    ),
    "not_received_header": (
        "Disculpa, no pudimos recibir {n} archivos:",
        "Sorry, we couldn't receive {n} files:",
    ),
    "not_received_header_one": (
        "Disculpa, no pudimos recibir este archivo.",
        "Sorry, we couldn't receive this file.",
    ),
    "not_received_closing": ("Envíalos como foto o PDF.", "Send them as a photo or PDF."),
    "not_received_closing_one": (
        "Envíalo como foto o PDF.",
        "Send it as a photo or PDF.",
    ),
    "not_received_more": ("• y {n} más", "• and {n} more"),
    "whatsapp_receipt_missing": (
        "Hola. Por aquí no respondemos mensajes, solo recibimos facturas.",
        "Hi. We don't answer messages here, we only receive invoices.",
    ),
    "send_here": (
        "Envía aquí la foto o el PDF de tus facturas.",
        "Send a photo or PDF of your invoices here.",
    ),
    "linked": (
        "Listo, este WhatsApp quedó conectado.",
        "Done, this WhatsApp is connected.",
    ),
    "whatsapp_link_code_invalid": (
        "Ese código venció o ya se usó. Crea uno nuevo en Cuadrao.",
        "That code has expired or was already used. Create a new one in Cuadrao.",
    ),
    "daily_cap": (
        "Por hoy no avisaremos más sobre archivos que no podamos recibir. Las facturas válidas siguen entrando.",
        "We won't send more alerts today about files we can't receive. Valid invoices keep coming in.",
    ),
}


def compose_reply(key: str, *, language: str | None, **values: str | int) -> str:
    index = 1 if language == "en" else 0
    body = REPLIES[key][index].format(**values)
    if key in ("linked", "whatsapp_receipt_missing"):
        return f"{body} {REPLIES['send_here'][index]}"
    return body


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
