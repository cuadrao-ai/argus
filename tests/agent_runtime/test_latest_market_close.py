"""Price lookups use the resolver's identity, including provider aliases and FX."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest
from argus.agent_runtime import knowledge_answer
from argus.agent_runtime.answer_calculation import latest_market_close
from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
from argus.domain.market_data import assets, provider
from faker import Faker


@pytest.fixture
def market_closes(monkeypatch: pytest.MonkeyPatch, faker: Faker) -> Mock:
    pairs = {
        "XXBTZUSD": {"base": "XXBT", "quote": "ZUSD", "wsname": "XBT/USD"},
        "ZEURZUSD": {"base": "ZEUR", "quote": "ZUSD", "wsname": "EUR/USD"},
        "ZUSDZJPY": {"base": "ZUSD", "quote": "ZJPY", "wsname": "USD/JPY"},
    }
    monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setattr(assets, "_ASSET_ALIAS_MAP", None)
    monkeypatch.setattr(assets, "_ASSET_CACHE_MODE", None)
    monkeypatch.setattr(assets, "_ASSET_CACHE_TS", 0.0)
    monkeypatch.setattr(
        assets, "_load_asset_universe", lambda: assets._load_kraken_asset_pairs(pairs)
    )
    series = pd.Series(
        [faker.pyfloat(min_value=1, max_value=100_000) for _ in range(2)],
        index=pd.bdate_range(end=faker.date_this_year(), periods=2),
    )
    closes = {
        ("BTC", "crypto"): series,
        ("EURUSD", "currency_pair"): series,
        ("USDJPY", "currency_pair"): series,
    }
    fetch = Mock(side_effect=lambda symbol, asset_class, *_: closes[symbol, asset_class])
    monkeypatch.setattr(provider, "fetch_price_series", fetch)
    return fetch


def test_bitcoin_alias_and_canonical_symbol_return_the_same_close(
    market_closes: Mock,
) -> None:
    canonical = latest_market_close("BTC")

    assert canonical is not None
    assert latest_market_close("XBT/USD") == canonical
    assert [call.args[:2] for call in market_closes.call_args_list] == [
        ("BTC", "crypto"),
        ("BTC", "crypto"),
    ]


@pytest.mark.parametrize("symbol", ["EUR/USD", "EURUSD"])
def test_currency_pair_returns_its_latest_close(market_closes: Mock, symbol: str) -> None:
    close = latest_market_close(symbol)

    assert close is not None
    assert market_closes.call_args.args[:2] == ("EURUSD", "currency_pair")
    series = market_closes.side_effect("EURUSD", "currency_pair")
    assert close == (series.iloc[-1], str(series.index[-1].date()))


def test_unknown_symbol_returns_none_without_fetching(market_closes: Mock) -> None:
    assert latest_market_close("UNKNOWN_SYMBOL") is None
    market_closes.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("symbol", "canonical", "asset_class"),
    [("XBT/USD", "BTC", "crypto"), ("EUR/USD", "EURUSD", "currency_pair")],
)
async def test_market_stats_fetches_the_resolved_identity(
    market_closes: Mock,
    monkeypatch: pytest.MonkeyPatch,
    faker: Faker,
    symbol: str,
    canonical: str,
    asset_class: str,
) -> None:
    answer = faker.sentence()
    voice = AsyncMock(return_value=answer)
    monkeypatch.setattr(knowledge_answer, "_voiced_answer", voice)

    result = await knowledge_answer._market_stats_answer(
        query=knowledge_answer.KnowledgeQueryExtraction(
            question_kind="market_stats", symbols=[symbol]
        ),
        interpretation=StructuredInterpretation(
            intent="unsupported_or_out_of_scope",
            task_relation="new_task",
            user_goal_summary=faker.sentence(),
        ),
        message=faker.sentence(),
        language="en",
    )

    assert result == answer
    assert market_closes.call_args.args[:2] == (canonical, asset_class)
    voice.assert_awaited_once()
