"""Stored email authentication verdicts retain their closed vocabulary."""

from uuid import uuid4

import psycopg
import pytest

from tests import test_business_email_intake_postgres as shared

actions = shared.actions
users = shared.users
rig = shared.rig
pytestmark = shared.pytestmark


@pytest.mark.parametrize(
    "verdict",
    [None, "aligned", "failed", "unknown", "ambiguous", "no_result", "none"],
)
def test_a_delivery_stores_every_auth_verdict(rig, verdict):
    delivery = rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
    with rig["pool"].connection() as db:
        db.execute(
            "update public.business_email_deliveries set auth_result=%s where id=%s",
            (verdict, delivery.id),
        )
        stored = db.execute(
            "select auth_result from public.business_email_deliveries where id=%s",
            (delivery.id,),
        ).fetchone()[0]
    assert stored == verdict


def test_a_delivery_refuses_an_unknown_auth_verdict(rig):
    delivery = rig["runtime"].enqueue_resend(str(uuid4()), (rig["route"].recipient,))
    with pytest.raises(psycopg.errors.CheckViolation), rig["pool"].connection() as db:
        db.execute(
            "update public.business_email_deliveries set auth_result='pass' where id=%s",
            (delivery.id,),
        )
