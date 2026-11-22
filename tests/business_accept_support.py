"""An accept as the web sends it once the person confirmed: it names every
Listos gap the dossier shows. A record with no gap names none."""

from __future__ import annotations

from uuid import UUID


def seen_gaps(service, context, draft_id: UUID | str) -> tuple[str, ...]:  # noqa: ANN001
    return service.dossier(context, UUID(str(draft_id))).listo_gaps


#: The gaps each accept named, by its URL and version. A replay is the same
#: request, so it names what the person saw then, not what the record shows now.
_NAMED: dict[tuple[str, int], list[str] | None] = {}


def accept(client, url: str, *, json: dict, headers: dict):  # noqa: ANN001, ANN201
    """POST the accept at ``url``, naming the gaps its draft shows this caller.
    A caller who cannot read the dossier names none."""

    request = (url, json["version"])
    if request not in _NAMED:
        dossier = client.get(f"{url.removesuffix('/approve')}/dossier", headers=headers)
        seen = dossier.json().get("listo_gaps") if dossier.status_code == 200 else None
        _NAMED.setdefault(request, seen)
    gaps = _NAMED[request]
    body = {**json, "accept_gaps": gaps} if gaps else json
    return client.post(url, json=body, headers=headers)


def accepting(dossier: dict, action: str) -> dict:
    """The accept body for the dossier a person has open: its version, and
    every gap it lists."""

    gaps = dossier.get("listo_gaps")
    named = {"accept_gaps": gaps} if gaps else {}
    return {"version": dossier["version"], "action": action, **named}
