"""A sender rule re-places that sender's held emails on real Postgres."""

from __future__ import annotations

from uuid import uuid4

from tests import test_business_email_intake_postgres as shared
from tests.ingestion.email_regroup_support import held_scenario

actions = shared.actions
users = shared.users
rig = shared.rig
pytestmark = shared.pytestmark


def test_a_rule_re_places_held_emails_on_postgres(rig):
    pool, store = rig["pool"], rig["store"]
    other = str(uuid4())
    with pool.connection() as db:
        db.execute(
            "insert into public.spaces(id,created_by,kind,name) "
            "values(%s,%s,'business','Otra')",
            (other, rig["users"]["other"]),
        )

    def place(delivery_id: str, **columns) -> None:  # noqa: ANN003
        names = ",".join(f"{key}=%s" for key in columns)
        with pool.connection() as db:
            db.execute(
                f"update public.business_email_deliveries set {names} where id=%s",
                (*columns.values(), delivery_id),
            )

    held_scenario(store, rig["route"], other, place)
