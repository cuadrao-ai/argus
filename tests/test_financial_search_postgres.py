"""Run the shared Search behavior matrix in the required PostgreSQL CI gate."""

import pytest

from tests.financial_accounts.test_financial_search import (
    scene as scene,
)
from tests.financial_accounts.test_financial_search import (
    test_accent_and_literal_search_queries as test_accent_and_literal_search_queries,
)
from tests.financial_accounts.test_financial_search import (
    test_archived_outside_forecast_expectation_is_findable_and_opens_exact_id as test_archived_outside_forecast_expectation_is_findable_and_opens_exact_id,
)
from tests.financial_accounts.test_financial_search import (
    test_logical_transfer_and_current_correction_only as test_logical_transfer_and_current_correction_only,
)
from tests.financial_accounts.test_financial_search import (
    test_snapshot_cursor_scope_staleness_and_stable_pages as test_snapshot_cursor_scope_staleness_and_stable_pages,
)

pytestmark = pytest.mark.parametrize("scene", ["postgres"], indirect=True)
