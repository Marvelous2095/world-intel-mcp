"""Unit tests for Eurozone & DAX macro data sources."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from world_intel_mcp.sources.eurozone import (
    _parse_eurostat_values,
    fetch_eurostat_macro,
    fetch_ecb_data,
    fetch_ifo_zew_sentiment,
)


@pytest.fixture
def mock_eurostat_json():
    return {
        "version": "2.0",
        "class": "dataset",
        "value": {"0": 2.2, "1": 1.8},
        "dimension": {
            "time": {
                "category": {
                    "label": {"2026M06": "2026-06", "2026M05": "2026-05"}
                }
            },
            "geo": {
                "category": {
                    "label": {"EA": "Euro area"}
                }
            }
        }
    }


def test_parse_eurostat_values(mock_eurostat_json):
    parsed = _parse_eurostat_values(mock_eurostat_json)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["value"] == 1.8 or parsed[0]["value"] == 2.2


@pytest.mark.asyncio
async def test_fetch_eurostat_macro(mock_eurostat_json):
    fetcher = MagicMock()
    fetcher.get_json = AsyncMock(return_value=mock_eurostat_json)

    res = await fetch_eurostat_macro(fetcher, indicators=["hicp"])
    assert res["source"] == "eurostat"
    assert "hicp_inflation" in res["indicators"]


@pytest.mark.asyncio
async def test_fetch_ecb_data():
    mock_ecb_response = {
        "dataSets": [
            {
                "series": {
                    "0:0:0:0:0": {
                        "observations": {
                            "0": [2.75],
                            "1": [3.00]
                        }
                    }
                }
            }
        ]
    }
    fetcher = MagicMock()
    fetcher.get_json = AsyncMock(return_value=mock_ecb_response)

    res = await fetch_ecb_data(fetcher)
    assert res["source"] == "ecb-data-portal"
    assert res["currency"] == "EUR"
    assert res["eur_usd_reference"] == 3.00


@pytest.mark.asyncio
async def test_fetch_ifo_zew_sentiment():
    fetcher = MagicMock()
    fetcher.get_text = AsyncMock(return_value="<rss><title>ifo Geschäftsklima Deutschland</title></rss>")

    res = await fetch_ifo_zew_sentiment(fetcher)
    assert res["source"] == "ifo-zew-aggregate"
    assert "ifo_business_climate" in res
    assert "zew_economic_sentiment" in res
