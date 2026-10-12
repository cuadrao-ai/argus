"""The WhatsApp replay, linking and isolation cases on real Postgres."""

from collections.abc import Iterator

import pytest
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.document_sources_support import source_objects
from tests.ingestion import whatsapp_cases as cases
from tests.ingestion.whatsapp_support import RefusingExtractor

users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)


@pytest.fixture
def pool() -> Iterator[ConnectionPool]:
    with ConnectionPool(shared.DSN, min_size=0, max_size=4) as opened:
        yield opened


def _world(pool: ConnectionPool, users: dict[str, str]) -> cases.World:
    clock = cases.Clock()
    connections = PostgresConnectionRepository(pool)
    hub = IngestionHub(connections, box=None, sink=None, clock=clock)
    documents = DocumentsService(hub, PostgresDocumentStore(pool, source_objects()), RefusingExtractor())
    return cases.build_world(
        documents=documents,
        store=PostgresWhatsAppStore(pool),
        clock=clock,
        alice=users["owner"],
        bob=users["other"],
        spaces=PostgresSpaceStore(pool),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", cases.CASES, ids=lambda case: case.__name__)
async def test_intake_case_on_postgres(case, pool, users) -> None:  # noqa: ANN001
    await case(_world(pool, users))


@pytest.mark.asyncio
async def test_english_link_gets_english_only(pool, users) -> None:  # noqa: ANN001
    await cases.english_owner_gets_english_only(_world(pool, users))


@pytest.mark.asyncio
async def test_link_language_wins_over_the_default_english_profile(pool, users) -> None:  # noqa: ANN001
    with pool.connection() as connection:
        [profile_language] = connection.execute(
            "select language from public.profiles where id = %s", (users["owner"],)
        ).fetchone()
    assert profile_language == "en"
    world = _world(pool, users)
    await world.link(world.alice, cases.ALICE_PHONE, "es-419")
    assert world.transport.bodies() == [
        "Listo, este WhatsApp quedó conectado. "
        "Envía aquí la foto o el PDF de tus recibos."
    ]
    with pool.connection() as connection:
        [stored] = connection.execute(
            "select reply_language from public.whatsapp_sender_links "
            "where destination_owner_id = %s and status = 'active'",
            (users["owner"],),
        ).fetchone()
    assert stored == "es-419"


def test_clients_cannot_read_or_write_whatsapp_tables(users) -> None:  # noqa: ANN001
    import psycopg

    with psycopg.connect(shared.DSN) as connection, connection.cursor() as cursor:
        shared._set_authenticated_claims(
            cursor, user_id=users["owner"], is_anonymous=False
        )
        for table in (
            "whatsapp_inbound_messages",
            "whatsapp_link_codes",
            "whatsapp_sender_links",
        ):
            cursor.execute("savepoint probe")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(f"select 1 from public.{table} limit 1")
            cursor.execute("rollback to savepoint probe")
        connection.rollback()
