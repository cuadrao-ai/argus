from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from argus.domain.business.contracts.recovery import BusinessModelOutputInvalid
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.whatsapp.business_capture import BusinessCaptureStore
from argus.domain.ingestion.whatsapp.business_delivery import BusinessDeliveryStore
from argus.domain.ingestion.whatsapp.business_envelope import EnvelopeCodec
from argus.domain.ingestion.whatsapp.business_outbox import BusinessOutbox
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore
from argus.domain.ingestion.whatsapp.business_worker import BusinessWhatsAppWorker
from argus.domain.ingestion.whatsapp.identity import WhatsAppKeys
from argus.domain.ingestion.whatsapp.payload import TextMessage
from faker import Faker
from psycopg.types.json import Jsonb

fake = Faker()


class ScriptedTransport:
    def __init__(self):
        self.messages = []
        self.fail = False

    async def send(self, payload):
        self.messages.append(payload)
        if self.fail:
            raise RuntimeError("synthetic transport outcome unknown")


class ScriptedActions:
    def __init__(self, turns, pool):
        self.turns, self.pool = turns, pool
        self.grant_id = uuid4()
        self.revoked = False
        self.waiting = []
        self.resolved_grants = []

    def resolve_actor(self, actor, *, grant_id=None):
        self.resolved_grants.append(grant_id)
        if self.revoked or (grant_id is not None and grant_id != self.grant_id):
            raise PermissionError("synthetic grant revoked")
        return SimpleNamespace(actor=actor, grant_id=self.grant_id)

    def plan_for_turn(self, context, key, *, lease):
        with self.pool.connection() as connection, connection.transaction():
            self.turns.require_lease(connection, lease)
        if self.revoked:
            raise PermissionError("synthetic grant revoked")
        turn = self.turns.load_turn(key)
        if turn.model_state == "unknown":
            raise RuntimeError("business_model_outcome_unknown")
        if turn.plan_actor and turn.plan_actor.grant_id != context.grant_id:
            raise PermissionError("synthetic original grant mismatch")
        return turn.plan

    def mark_turn_waiting_for_window(self, context, key, *, lease):
        self.plan_for_turn(context, key, lease=lease)
        self.waiting.append(key)

    def persist_synthetic_plan(self, turn, context):
        actor = {
            "actor_id": str(turn.actor_id),
            "actor_kind": "owner_via_agent",
            "display_name": "Synthetic owner",
            "grant_id": str(context.grant_id),
            "issuer_id": str(turn.actor_id),
            "issuer_display_name": "Synthetic owner",
        }
        with self.pool.connection() as connection:
            connection.execute(
                "update public.business_turns set plan=%s,plan_actor=%s,model_state='completed' where turn_key=%s",
                (
                    Jsonb({"schema_version": 1, "actions": []}),
                    Jsonb(actor),
                    turn.turn_key,
                ),
            )


class ScriptedExecutor:
    def __init__(self, actions):
        self.actions = actions
        self.interpretations = []
        self.compositions = 0
        self.histories = []
        self.reply = "Guardé el borrador para revisión."
        self.fail_before_plan = False
        self.invalid_output = False
        self.fail_composition = False

    async def __call__(
        self, *, captured, turn, lease, authorization, begin_reply, history
    ):
        self.histories.append(history)
        if turn.plan is None:
            self.interpretations.append(captured.envelope.text)
            if self.invalid_output:
                raise BusinessModelOutputInvalid()
            if self.fail_before_plan:
                raise RuntimeError("synthetic interrupted interpretation")
            with self.actions.pool.connection() as connection:
                connection.execute(
                    "insert into public.business_sources(space_id,kind,channel,source_key,text_content,received_at)"
                    " values (%s,'message','whatsapp',%s,%s,%s) on conflict (space_id,source_key) do nothing",
                    (
                        captured.space_id,
                        f"message:whatsapp:{captured.id}",
                        captured.envelope.text,
                        captured.received_at,
                    ),
                )
            self.actions.persist_synthetic_plan(turn, authorization)
        saved = begin_reply()
        if saved is not None:
            return saved
        self.compositions += 1
        if self.fail_composition:
            raise RuntimeError("synthetic interrupted composition")
        return self.reply


@dataclass
class World:
    pool: object
    owner: UUID
    space: UUID
    link: UUID
    keys: WhatsAppKeys
    captures: BusinessCaptureStore
    turns: BusinessTurnStore
    outbox: BusinessOutbox
    delivery: BusinessDeliveryStore
    transport: ScriptedTransport
    actions: ScriptedActions
    executor: ScriptedExecutor

    def message(self, text="Compré materiales por 850", *, sent_at=None):
        return TextMessage(
            fake.uuid4(), "15550101234", sent_at or datetime.now(timezone.utc), text
        )

    def worker(self, *, synthetic_consent=False):
        return BusinessWhatsAppWorker(
            captures=self.captures,
            turns=self.turns,
            outbox=self.outbox,
            delivery=self.delivery,
            transport=self.transport,
            actions=self.actions,
            execute_turn=self.executor,
            has_consent=lambda space, owner: synthetic_consent,
        )

    def states(self, message):
        with self.pool.connection() as connection:
            return connection.execute(
                "select state from public.whatsapp_outbox where provider_message_key=%s order by reply_index",
                (self.keys.message(message.id),),
            ).fetchall()


def build_world(pool, owner, space):
    keys = WhatsAppKeys(fake.password(length=32))
    with pool.connection() as connection:
        link = connection.execute(
            "insert into public.whatsapp_sender_links(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values (%s,%s,'1234','es-419','active',clock_timestamp()) returning id",
            (owner, keys.sender("15550101234")),
        ).fetchone()[0]
    turns = BusinessTurnStore(pool)
    actions = ScriptedActions(turns, pool)
    with pool.connection() as connection:
        # A new space is born with the owner's own grant; this world uses its own.
        connection.execute(
            "update public.business_client_grants set revoked_at=clock_timestamp()"
            " where space_id=%s and grantee_id=%s and revoked_at is null",
            (space, owner),
        )
        connection.execute(
            "insert into public.business_client_grants(id,space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,%s,array['read','prepare'])",
            (actions.grant_id, space, owner, owner),
        )
    return World(
        pool,
        UUID(owner),
        space,
        link,
        keys,
        BusinessCaptureStore(pool, EnvelopeCodec(SecretBox(bytes(range(32))), keys)),
        turns,
        BusinessOutbox(pool),
        BusinessDeliveryStore(pool),
        ScriptedTransport(),
        actions,
        ScriptedExecutor(actions),
    )
