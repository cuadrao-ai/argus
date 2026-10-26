from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.reporting_views import (
    CreateView,
    UpdateView,
    delete_view,
    list_views,
    save_view,
)

from tests import test_business_actions_postgres as shared
from tests.test_business_reporting_postgres import viewer_context

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


def test_private_recipe_survives_reread_and_replay_without_result_cache(actions, users):
    service, context, _ = actions
    command = CreateView(
        name="Purchases",
        recipe={
            "filters": {"period": {"kind": "this_month"}},
            "columns": ["counterparty", "gross_amount"],
        },
    )
    key = str(uuid4())
    first = save_view(service.authority, context, command, key)
    assert save_view(service.authority, context, command, key) == first
    [saved] = list_views(service.authority, context)
    assert saved.recipe.filters.period.kind == "this_month"
    assert saved.recipe.columns == ("counterparty", "gross_amount")
    assert saved.version == 1
    viewer = viewer_context(service, context, users["other"])
    assert list_views(service.authority, viewer) == ()
    with pytest.raises(ActionError, match="business_report_view_not_found"):
        save_view(
            service.authority,
            viewer,
            UpdateView(name="Other", recipe={}, expected_version=1),
            str(uuid4()),
            first.id,
        )
    with pytest.raises(ActionError, match="idempotency_conflict"):
        save_view(
            service.authority,
            context,
            command.model_copy(update={"name": "Changed"}),
            key,
        )


def test_concurrent_versioned_edits_cannot_overwrite_each_other(actions):
    service, context, _ = actions
    first = save_view(service.authority, context, CreateView(name="One"), str(uuid4()))

    def update(name):
        try:
            return save_view(
                service.authority,
                context,
                UpdateView(name=name, expected_version=1),
                str(uuid4()),
                first.id,
            )
        except ActionError as error:
            return error.result.code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(update, ["Two", "Three"]))
    assert sum(result == "business_report_view_changed" for result in results) == 1
    [latest] = list_views(service.authority, context)
    assert latest.version == 2
    key = str(uuid4())
    delete_view(service.authority, context, latest.id, 2, key)
    delete_view(service.authority, context, latest.id, 2, key)
    assert list_views(service.authority, context) == ()


def test_revoked_grant_cannot_read_or_replay_private_view(actions, users):
    service, context, _ = actions
    viewer = viewer_context(service, context, users["other"])
    key = str(uuid4())
    command = CreateView(name="Personal")
    save_view(service.authority, viewer, command, key)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
            (viewer.grant_id,),
        )
    with pytest.raises(ActionError):
        list_views(service.authority, viewer)
    with pytest.raises(ActionError):
        save_view(service.authority, viewer, command, key)


def test_client_roles_have_no_direct_view_or_receipt_access(actions):
    service, _, _ = actions
    with service.authority.pool.connection() as db:
        for role in ("anon", "authenticated"):
            for table in ("business_saved_report_views", "business_report_view_commands"):
                assert not db.execute(
                    "select has_table_privilege(%s,%s,%s)",
                    (role, "argus_private." + table, "select,insert,update,delete"),
                ).fetchone()[0]
                assert db.execute(
                    "select relrowsecurity from pg_class where oid=%s::regclass",
                    ("argus_private." + table,),
                ).fetchone()[0]
