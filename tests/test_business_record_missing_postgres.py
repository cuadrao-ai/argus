from __future__ import annotations

from types import SimpleNamespace

import pytest
from faker import Faker

from tests import test_business_fiscal_routes_postgres as routes
from tests.test_business_approve_unpaid_postgres import _get, _recorded
from tests.test_business_personal_mark_postgres import _registros

world = routes.world
pytestmark = [routes.pytestmark, pytest.mark.usefixtures("typed_notes_on")]


def test_registros_returns_the_dossiers_missing_reasons(
    world: SimpleNamespace, faker: Faker
) -> None:
    draft, _ = _recorded(world, "expense", faker.numerify("B01########"))
    dossier = _get(world, f"/business/drafts/{draft}/dossier").json()
    [row] = _registros(world)["items"]

    assert row["draft_id"] == draft
    assert "expense_type_missing" in dossier["missing"]
    assert row["missing"] == dossier["missing"]
    assert row["ready"] is False
    assert row.get("reasons") == dossier["reasons"]
