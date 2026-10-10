from __future__ import annotations

from psycopg import Connection

from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.ingestion.reconcile.model import EventNotFound, ImportEvent, Observation
from argus.domain.ingestion.reconcile.store_postgres import _PostgresTx


class LegacyImportTransaction(_PostgresTx):
    def __init__(self, connection: Connection, context: ActionContext) -> None:
        super().__init__(connection, context.owner_id, context.scope)
        self.context = context
        self.changed_events: set[str] = set()
        self.changed_connections: set[str] = set()

    def require_legacy(self, event_id: str) -> None:
        try:
            event = self.event(event_id)
        except EventNotFound:
            return
        if "business" in event.resolution:
            raise ActionError("invalid_input", "business_action_required")

    def put_event(self, event: ImportEvent) -> None:
        self.require_legacy(event.id)
        if "business" in event.resolution:
            raise ActionError("invalid_input", "business_action_required")
        self.changed_events.add(event.id)
        super().put_event(event)

    def put_observation(self, observation: Observation) -> None:
        self.require_legacy(observation.event_id)
        self.changed_connections.add(observation.connection_id)
        super().put_observation(observation)

    def delete_event(self, event_id: str) -> None:
        self.require_legacy(event_id)
        super().delete_event(event_id)

    def verify_links(self) -> None:
        if not self.changed_events and not self.changed_connections:
            return
        conflicts = self._rows(
            "select e.id from public.financial_import_events e"
            " join public.financial_import_observations o on o.event_id=e.id"
            " join public.business_sources s on s.connection_id=o.connection_id and s.space_id=e.owner_space_id"
            " join public.business_draft_sources l on l.source_id=s.id and l.space_id=s.space_id"
            " join public.financial_import_events typed on typed.id=l.draft_id and typed.owner_space_id=l.space_id"
            " where e.owner_space_id=%s and e.user_id=%s and typed.user_id=e.user_id"
            " and typed.resolution ? 'business' and typed.id<>e.id"
            " and (e.id=any(%s::uuid[]) or o.connection_id=any(%s::uuid[])) limit 1",
            (
                self.context.actor.space_id,
                self.context.owner_id,
                list(self.changed_events),
                list(self.changed_connections),
            ),
        )
        if conflicts:
            raise ActionError("invalid_input", "business_action_required")
