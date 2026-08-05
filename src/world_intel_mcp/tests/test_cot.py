"""Unit tests for CFTC Commitments of Traders (COT) source module."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from world_intel_mcp.sources.cot import (
    COT_MARKETS,
    _calculate_metrics,
    fetch_cot_positioning,
    fetch_cot_extremes,
    fetch_cot_history,
)


@pytest.fixture
def mock_cftc_records():
    return [
        {
            "report_date_as_yyyy_mm_dd": "2026-08-01T00:00:00.000",
            "market_and_exchange_names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
            "noncomm_positions_long_all": "120000",
            "noncomm_positions_short_all": "80000",
            "comm_positions_long_all": "50000",
            "comm_positions_short_all": "90000",
        },
        {
            "report_date_as_yyyy_mm_dd": "2026-07-25T00:00:00.000",
            "market_and_exchange_names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
            "noncomm_positions_long_all": "115000",
            "noncomm_positions_short_all": "82000",
            "comm_positions_long_all": "51000",
            "comm_positions_short_all": "88000",
        },
        {
            "report_date_as_yyyy_mm_dd": "2026-07-18T00:00:00.000",
            "market_and_exchange_names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
            "noncomm_positions_long_all": "90000",
            "noncomm_positions_short_all": "100000",
            "comm_positions_long_all": "60000",
            "comm_positions_short_all": "70000",
        },
    ]


def test_market_mapping_coverage():
    assert "EUR" in COT_MARKETS
    assert "GOLD" in COT_MARKETS
    assert "WTI" in COT_MARKETS
    assert "DAX" in COT_MARKETS
    assert len(COT_MARKETS) >= 10


def test_calculate_metrics(mock_cftc_records):
    metrics = _calculate_metrics(mock_cftc_records)
    assert metrics is not None
    assert metrics["report_date"] == "2026-08-01"
    assert metrics["non_commercials"]["long"] == 120000
    assert metrics["non_commercials"]["short"] == 80000
    assert metrics["non_commercials"]["net"] == 40000
    assert metrics["commercials"]["net"] == -40000
    assert 0.0 <= metrics["cot_index"] <= 100.0
    assert isinstance(metrics["z_score"], float)
    assert metrics["signal"] in ["EXTREME_LONG", "EXTREME_SHORT", "NEUTRAL"]


@pytest.mark.asyncio
async def test_fetch_cot_positioning(mock_cftc_records):
    fetcher = MagicMock()
    fetcher.get_json = AsyncMock(return_value=mock_cftc_records)

    res = await fetch_cot_positioning(fetcher, markets=["EUR"])
    assert res["source"] == "cftc-soda"
    assert "EUR" in res["markets"]
    eur = res["markets"]["EUR"]
    assert eur["market"] == "EUR"
    assert eur["non_commercials"]["net"] == 40000


@pytest.mark.asyncio
async def test_fetch_cot_extremes(mock_cftc_records):
    fetcher = MagicMock()
    fetcher.get_json = AsyncMock(return_value=mock_cftc_records)

    res = await fetch_cot_extremes(fetcher, threshold=1.0)
    assert "extreme_long" in res
    assert "extreme_short" in res
    assert "threshold" in res
    assert res["threshold"] == 1.0


@pytest.mark.asyncio
async def test_fetch_cot_history(mock_cftc_records):
    fetcher = MagicMock()
    fetcher.get_json = AsyncMock(return_value=mock_cftc_records)

    res = await fetch_cot_history(fetcher, market="EUR", weeks=3)
    assert res["market"] == "EUR"
    assert res["records_count"] == 3
    assert len(res["history"]) == 3
