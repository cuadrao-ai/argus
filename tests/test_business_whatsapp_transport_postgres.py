from uuid import uuid4

import pytest
from faker import Faker

from tests import test_whatsapp_ai_consent_postgres as shared
from tests.business_cleanup import delete_spaces

users, pool, world = shared.users, shared.pool, shared.world
pytestmark = shared.pytestmark


@pytest.mark.parametrize("parent", ["link", "space", "account"])
def test_historical_message_source_follows_the_business_after_link_or_owner_removal(
    world, parent
):
    text = Faker().sentence()
    with world.pool.connection() as db:
        source = db.execute(
            "insert into public.business_sources(space_id,kind,channel,source_key,text_content,received_at)"
            " values (%s,'message','whatsapp',%s,%s,clock_timestamp()) returning id",
            (world.space, str(uuid4()), text),
        ).fetchone()[0]
        if parent == "link":
            db.execute(
                "delete from public.whatsapp_sender_links where id=%s", (world.link,)
            )
        elif parent == "space":
            delete_spaces(db, "id=%s", (world.space,))
        else:
            from tests.test_business_account_deletion_postgres import (
                erase_open_owner,
                release_custodian,
            )

            db.commit()
            outcome = erase_open_owner(world.pool, world.owner)
            assert outcome.status == "done"

        original = db.execute(
            "select text_content from public.business_sources where id=%s", (source,)
        ).fetchone()
        assert original == (None if parent == "space" else (text,))
        if parent == "account":
            release_custodian(world.space)


def test_transport_tables_are_server_only_and_truncate_is_denied(pool):
    with pool.connection() as connection:
        assert connection.execute(
            "select relrowsecurity from pg_class where oid='public.whatsapp_outbox'::regclass"
        ).fetchone() == (True,)
        for role in ("anon", "authenticated"):
            for relation in ("whatsapp_outbox", "whatsapp_inbound_messages"):
                assert connection.execute(
                    "select has_table_privilege(%s,%s,%s)",
                    (role, f"public.{relation}", "SELECT,INSERT,UPDATE,DELETE,TRUNCATE"),
                ).fetchone() == (False,)
        assert connection.execute(
            "select has_table_privilege('service_role','public.whatsapp_outbox','SELECT,INSERT,UPDATE,DELETE')"
        ).fetchone() == (True,)
        for relation in ("whatsapp_outbox", "whatsapp_inbound_messages"):
            assert connection.execute(
                "select has_table_privilege(%s,%s,%s)",
                ("service_role", f"public.{relation}", "TRUNCATE"),
            ).fetchone() == (False,)
