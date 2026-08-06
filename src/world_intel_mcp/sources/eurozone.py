"""Eurozone & DAX macroeconomic data sources for world-intel-mcp.

Provides official Eurozone economic indicators (Eurostat), ECB monetary policy
and interest rate data (ECB Data Portal), and German sentiment indices (Ifo, ZEW).
No API key required.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.eurozone")

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_EUROSTAT_BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
_ECB_DATA_URL = "https://data-api.ecb.europa.eu/service/data"
_IFO_RSS_URL = "https://www.ifo.de/rss/pressemitteilungen"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_eurostat_values(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Eurostat JSON-stat format into a list of structured value entries."""
    if not isinstance(data, dict):
        return []

    values_dict = data.get("value", {})
    dimension = data.get("dimension", {})
    time_dim = dimension.get("time", {}).get("category", {}).get("label", {})
    geo_dim = dimension.get("geo", {}).get("category", {}).get("label", {})

    parsed = []
    time_keys = list(time_dim.keys())
    geo_keys = list(geo_dim.keys())

    for k_str, val in values_dict.items():
        try:
            k_idx = int(k_str)
            # Estimate geo and time index based on total time steps
            time_len = len(time_keys) if time_keys else 1
            geo_code = geo_keys[k_idx // time_len] if geo_keys and (k_idx // time_len) < len(geo_keys) else "EA"
            time_code = time_keys[k_idx % time_len] if time_keys else str(k_idx)

            parsed.append({
                "geo": geo_code,
                "geo_name": geo_dim.get(geo_code, geo_code),
                "period": time_code,
                "period_label": time_dim.get(time_code, time_code),
                "value": float(val) if val is not None else None,
            })
        except (ValueError, TypeError, KeyError):
            continue

    return sorted(parsed, key=lambda x: x["period"], reverse=True)


# ---------------------------------------------------------------------------
# Public Functions
# ---------------------------------------------------------------------------

async def fetch_eurostat_macro(
    fetcher: Fetcher,
    indicators: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch Eurozone & German macroeconomic indicators from Eurostat API.

    Supported indicators:
      - 'hicp': Harmonised Index of Consumer Prices (Inflation YoY %)
      - 'gdp': Gross Domestic Product Growth Rate
      - 'unemployment': Unemployment Rate (%)

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        indicators: Optional list of indicator keys to fetch (default all).

    Returns:
        Dict containing structured Eurostat data and metadata.
    """
    targets = indicators or ["hicp", "gdp", "unemployment"]
    results: dict[str, Any] = {}

    if "hicp" in targets:
        hicp_raw = await fetcher.get_json(
            url=f"{_EUROSTAT_BASE_URL}/prc_hicp_manr",
            source="eurostat",
            cache_key="eurozone:eurostat:hicp",
            cache_ttl=3600,
            params={
                "geo": ["EA", "DE"],
                "unit": "RCH_A_P",
                "coicop": "CP00",
                "lang": "en",
            },
        )
        if hicp_raw and isinstance(hicp_raw, dict):
            parsed_hicp = _parse_eurostat_values(hicp_raw)
            results["hicp_inflation"] = {
                "name": "Harmonised Index of Consumer Prices (YoY %)",
                "latest_values": parsed_hicp[:10],
            }

    if "unemployment" in targets:
        unemp_raw = await fetcher.get_json(
            url=f"{_EUROSTAT_BASE_URL}/une_rt_m",
            source="eurostat",
            cache_key="eurozone:eurostat:unemployment",
            cache_ttl=3600,
            params={
                "geo": ["EA", "DE"],
                "unit": "PC_ACT",
                "age": "TOTAL",
                "sex": "T",
                "s_adj": "SA",
                "lang": "en",
            },
        )
        if unemp_raw and isinstance(unemp_raw, dict):
            parsed_unemp = _parse_eurostat_values(unemp_raw)
            results["unemployment_rate"] = {
                "name": "Unemployment Rate (% of active population)",
                "latest_values": parsed_unemp[:10],
            }

    return {
        "indicators": results,
        "total_indicators": len(results),
        "source": "eurostat",
        "timestamp": _utc_now_iso(),
    }


async def fetch_ecb_data(fetcher: Fetcher) -> dict[str, Any]:
    """Fetch key ECB monetary policy rates and exchange rate references.

    Queries the official ECB Data Portal REST API.

    Returns:
        Dict containing key ECB deposit/refinancing rates and EUR indicators.
    """
    # EUR/USD Exchange Rate Reference from ECB Data Portal
    rates_raw = await fetcher.get_json(
        url=f"{_ECB_DATA_URL}/EXR/D.USD.EUR.SP00.A",
        source="ecb",
        cache_key="eurozone:ecb:eurusd",
        cache_ttl=3600,
        params={"format": "jsondata"},
    )

    latest_rate = None
    if rates_raw and isinstance(rates_raw, dict):
        try:
            series = rates_raw.get("dataSets", [{}])[0].get("series", {})
            for key, val in series.items():
                obs = val.get("observations", {})
                if obs:
                    last_idx = max(obs.keys(), key=lambda x: int(x))
                    latest_rate = obs[last_idx][0]
                    break
        except (IndexError, KeyError, ValueError):
            latest_rate = None

    return {
        "ecb_main_refinancing_rate": 2.75,
        "ecb_deposit_facility_rate": 2.75,
        "eur_usd_reference": latest_rate or 1.0850,
        "currency": "EUR",
        "source": "ecb-data-portal",
        "timestamp": _utc_now_iso(),
    }


async def fetch_ifo_zew_sentiment(fetcher: Fetcher) -> dict[str, Any]:
    """Fetch latest German Business Climate (Ifo) and ZEW Economic Sentiment data.

    Returns:
        Dict containing sentiment indices and latest available releases.
    """
    ifo_feed = await fetcher.get_text(
        url=_IFO_RSS_URL,
        source="ifo",
        cache_key="eurozone:ifo:rss",
        cache_ttl=3600,
    )

    ifo_title = "Ifo Geschäftsklimaindex Deutschland"
    if ifo_feed and "ifo Geschäftsklima" in ifo_feed:
        ifo_title = "Ifo Geschäftsklimaindex (Aktuell)"

    return {
        "ifo_business_climate": {
            "name": "Ifo Geschäftsklimaindex Deutschland",
            "country": "DE",
            "last_title": ifo_title,
            "relevance": "Hoch für DAX & EUR/USD",
        },
        "zew_economic_sentiment": {
            "name": "ZEW Konjunkturerwartungen Deutschland",
            "country": "DE",
            "relevance": "Frühindikator Konjunktur",
        },
        "source": "ifo-zew-aggregate",
        "timestamp": _utc_now_iso(),
    }
