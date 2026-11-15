"""Retired conversation search must not load the investing display backend."""

from pathlib import Path

from scripts.check_production_dependencies import import_graph, import_paths
from tests.test_conversation_surfaces import ALICE, _as, _start_space, client

_ = client


def test_conversation_search_is_retired(client) -> None:
    _start_space(ALICE)
    response = client.get(
        "/api/v1/search", params={"q": "receipt", "surface": "business"}, headers=_as(ALICE)
    )
    assert response.status_code == 404


def test_production_entry_points_do_not_reach_investing_search() -> None:
    graph, _ = import_graph(Path(__file__).resolve().parents[1])
    retired = {
        "argus.api.backtest_service",
        "argus.api.memory_run_dossiers",
        "argus.api.public_excerpt_selection",
        "argus.api.public_excerpts",
        "argus.api.routers.search",
        "argus.domain.conversation_recall",
        "argus.domain.public_excerpt_turns",
        "argus.domain.result_money",
        "argus.agent_runtime.retest_confirmation",
    }
    for entry in (
        "argus.api.main",
        "workflows.document_worker",
        "argus.api.routers.whatsapp",
        "argus.api.whatsapp_worker",
        "argus.agent_runtime.business.runner",
    ):
        assert entry in graph
        assert retired.isdisjoint(import_paths(graph, entry))
