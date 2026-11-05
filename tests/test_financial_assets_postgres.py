"""Owner access and atomic asset history on the existing disposable database."""

import json
import os
from uuid import uuid4

import pytest
from argus.domain.recording.asset_schemas import AssetDetailsRequest
from argus.domain.recording.assets import AssetService
from argus.domain.recording.service import FinancialAccountService
from psycopg.errors import InsufficientPrivilege

from tests.financial_accounts.test_assets import create
from tests.test_financial_accounts_postgres import repository as repository
from tests.test_financial_accounts_postgres import users as users

pytestmark = pytest.mark.skipif(
    not os.getenv("ARGUS_DISPOSABLE_DATABASE_URL"), reason="Disposable database required"
)


def test_asset_history_is_owner_read_only(repository, users):  # noqa: F811
    service = FinancialAccountService(repository)
    asset = create(service, users["owner"])
    debt = create(service, users["owner"], "other_debt", None, 10000)
    AssetService(service).details(
        users["owner"],
        asset.account.id,
        AssetDetailsRequest(
            expected_version=1,
            ownership_share_bps=5000,
            related_debt_account_id=debt.account.id,
        ),
        str(uuid4()),
    )
    for owner, anonymous, count in [
        (users["owner"], False, 1),
        (users["other"], False, 0),
        (users["guest"], True, 0),
    ]:
        with repository._pool.connection() as connection, connection.transaction():
            connection.execute("set local role authenticated")
            connection.execute(
                "select set_config('request.jwt.claims',%s,true)",
                (
                    json.dumps(
                        {"sub": owner, "role": "authenticated", "is_anonymous": anonymous}
                    ),
                ),
            )
            for table in ["financial_asset_details", "financial_asset_changes"]:
                assert (
                    connection.execute(
                        f"select count(*) from public.{table} where account_id=%s",
                        (asset.account.id,),
                    ).fetchone()[0]
                    == count
                )
                with pytest.raises(InsufficientPrivilege), connection.transaction():
                    connection.execute(
                        f"delete from public.{table} where account_id=%s",
                        (asset.account.id,),
                    )
