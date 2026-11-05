"""One activity claim may also fulfill one explicitly selected occurrence."""

from typing import Any


def protected_links(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Recurrence guards see all canonical claims without publishing foreign facts."""
    return state["links"] | {
        link["claim_id"]: link
        for link in state.get("_shared_links", [])
        if link["occurrence_id"]
    }


def occurrence_id(key: str, link: dict[str, Any]) -> str | None:
    return link.get("occurrence_id", key if link.get("expectation_id") else None)


def for_occurrence(state: dict[str, Any], identifier: str) -> dict[str, Any] | None:
    return next(
        (
            link
            for key, link in state["links"].items()
            if occurrence_id(key, link) == identifier
        ),
        None,
    )
