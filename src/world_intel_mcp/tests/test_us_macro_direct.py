"""Unit tests for direct US macroeconomic release data sources."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from world_intel_mcp.sources.us_macro_direct import (
    BLS_SERIES_MAP,
    _parse_bls_series,
    fetch_bls_releases,
    fetch_bea_pce_gdp,
)


@pytest.fixture
def mock_bls_json():
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "PAYEMS",
                    "data": [
                        {
                            "year": "2026",
                            "period": "M06",
                            "periodName": "June",
                            "value": "158500",
                            "footnotes": [],
                        },
                        {
                            "year": "2026",
                            "period": "M05",
                            "periodName": "May",
                            "value": "158300",
                            "footnotes": [],
                        },
                    ],
                }
            ]
        },
    }


def test_bls_series_map_coverage():
    assert "NFP" in BLS_SERIES_MAP
    assert "CPI" in BLS_SERIES_MAP
    assert "PPI" in BLS_SERIES_MAP
    assert "UNEMPLOYMENT" in BLS_SERIES_MAP


def test_parse_bls_series(mock_bls_json):
    series_data = mock_bls_json["Results"]["series"][0]
    parsed = _parse_bls_series(series_data)
    assert len(parsed) == 2
    assert parsed[0]["period_name"] == "June"
    assert parsed[0]["value"] == 158500.0


@pytest.mark.asyncio
async def test_fetch_bls_releases(mock_bls_json):
    fetcher = MagicMock()
    fetcher.post_json = AsyncMock(return_value=mock_bls_json)

    res = await fetch_bls_releases(fetcher, series_keys=["NFP"])
    assert res["source"] == "bls-gov"
    assert "NFP" in res["releases"]
    nfp = res["releases"]["NFP"]
    assert nfp["latest"]["value"] == 158500.0
    assert nfp["change_mom"] == 200.0


@pytest.mark.asyncio
async def test_fetch_bea_pce_gdp(mock_bls_json):
    fetcher = MagicMock()
    fetcher.post_json = AsyncMock(return_value=mock_bls_json)

    res = await fetch_bea_pce_gdp(fetcher)
    assert res["source"] == "bea-bls-aggregate"
    assert "pce_headline_yoy" in res
    assert "real_gdp_qom" in res
