"""CFTC Commitments of Traders (COT) data sources for world-intel-mcp.

Provides institutional positioning analysis for forex, commodities, and index futures
via the official CFTC SODA API and FuturesBench API. No API key required.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from ..fetcher import Fetcher

logger = logging.getLogger("world-intel-mcp.sources.cot")

# ---------------------------------------------------------------------------
# Constants & Market Mappings
# ---------------------------------------------------------------------------

_CFTC_SODA_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
_FUTURESBENCH_URL = "https://futuresbench.com/api/v1/latest.json"

COT_MARKETS: dict[str, str] = {
    "EUR": "EURO FX",
    "GBP": "BRITISH POUND",
    "JPY": "JAPANESE YEN",
    "CHF": "SWISS FRANC",
    "GOLD": "GOLD",
    "SILVER": "SILVER",
    "WTI": "CRUDE OIL",
    "COPPER": "COPPER",
    "WHEAT": "WHEAT",
    "SP500": "E-MINI S&P 500",
    "DAX": "DAX",
    "NASDAQ": "NASDAQ-100",
    "VIX": "VIX",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calculate_metrics(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Calculate net positioning, COT index, Z-score and signal from raw CFTC records."""
    if not records:
        return None

    current = records[0]
    date_str = current.get("report_date_as_yyyy_mm_dd") or current.get("date", "")

    try:
        nc_long = int(float(current.get("noncomm_positions_long_all") or current.get("non_commercial_long", 0)))
        nc_short = int(float(current.get("noncomm_positions_short_all") or current.get("non_commercial_short", 0)))
        comm_long = int(float(current.get("comm_positions_long_all") or current.get("commercial_long", 0)))
        comm_short = int(float(current.get("comm_positions_short_all") or current.get("commercial_short", 0)))
    except (ValueError, TypeError):
        return None

    net_nc = nc_long - nc_short
    net_comm = comm_long - comm_short

    # Extract historical net non-commercial positions to compute Z-score & COT index
    hist_nets = []
    for r in records:
        try:
            l = int(float(r.get("noncomm_positions_long_all") or r.get("non_commercial_long", 0)))
            s = int(float(r.get("noncomm_positions_short_all") or r.get("non_commercial_short", 0)))
            hist_nets.append(l - s)
        except (ValueError, TypeError):
            continue

    if len(hist_nets) > 1:
        min_net = min(hist_nets)
        max_net = max(hist_nets)
        range_net = max_net - min_net
        cot_index = round(((net_nc - min_net) / range_net * 100), 1) if range_net > 0 else 50.0

        avg_net = sum(hist_nets) / len(hist_nets)
        variance = sum((x - avg_net) ** 2 for x in hist_nets) / len(hist_nets)
        std_dev = variance ** 0.5
        z_score = round((net_nc - avg_net) / std_dev, 2) if std_dev > 0 else 0.0
        net_change_wow = net_nc - hist_nets[1] if len(hist_nets) > 1 else 0
    else:
        cot_index = 50.0
        z_score = 0.0
        net_change_wow = 0

    if z_score >= 1.5:
        signal = "EXTREME_LONG"
    elif z_score <= -1.5:
        signal = "EXTREME_SHORT"
    else:
        signal = "NEUTRAL"

    return {
        "report_date": date_str[:10],
        "commercials": {
            "long": comm_long,
            "short": comm_short,
            "net": net_comm,
        },
        "non_commercials": {
            "long": nc_long,
            "short": nc_short,
            "net": net_nc,
        },
        "cot_index": cot_index,
        "z_score": z_score,
        "net_change_wow": net_change_wow,
        "signal": signal,
    }


# ---------------------------------------------------------------------------
# Public Functions
# ---------------------------------------------------------------------------

async def fetch_cot_positioning(
    fetcher: Fetcher,
    markets: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch latest COT positioning metrics for specified markets (or all default).

    Args:
        fetcher: Shared HTTP fetcher with caching and circuit breaking.
        markets: Optional list of market symbols (e.g., ["EUR", "GOLD", "WTI"]).

    Returns:
        Dict mapping market symbol to structured positioning data.
    """
    target_markets = markets if markets else list(COT_MARKETS.keys())
    results: dict[str, Any] = {}

    for symbol in target_markets:
        search_term = COT_MARKETS.get(symbol.upper(), symbol)

        data = await fetcher.get_json(
            url=_CFTC_SODA_URL,
            source="cftc",
            cache_key=f"cot:positioning:{symbol.upper()}",
            cache_ttl=3600,
            params={
                "$limit": "52",
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$where": f"upper(market_and_exchange_names) like '%{search_term.upper()}%'",
            },
        )

        if data and isinstance(data, list) and len(data) > 0:
            metrics = _calculate_metrics(data)
            if metrics:
                results[symbol.upper()] = {
                    "market": symbol.upper(),
                    "name": search_term,
                    **metrics,
                }

    return {
        "markets": results,
        "total_markets": len(results),
        "source": "cftc-soda",
        "timestamp": _utc_now_iso(),
    }


async def fetch_cot_extremes(
    fetcher: Fetcher,
    threshold: float = 1.5,
) -> dict[str, Any]:
    """Screen for markets displaying extreme institutional positioning (|Z-score| >= threshold).

    Args:
        fetcher: Shared HTTP fetcher.
        threshold: Absolute Z-score threshold for extreme positioning (default 1.5).

    Returns:
        Dict containing extreme_long, extreme_short, and summary metrics.
    """
    all_pos = await fetch_cot_positioning(fetcher)
    markets_data = all_pos.get("markets", {})

    extreme_long = []
    extreme_short = []

    for symbol, m in markets_data.items():
        z = m.get("z_score", 0.0)
        if z >= threshold:
            extreme_long.append(m)
        elif z <= -threshold:
            extreme_short.append(m)

    return {
        "threshold": threshold,
        "extreme_long_count": len(extreme_long),
        "extreme_short_count": len(extreme_short),
        "extreme_long": extreme_long,
        "extreme_short": extreme_short,
        "source": "cftc-soda",
        "timestamp": _utc_now_iso(),
    }


async def fetch_cot_history(
    fetcher: Fetcher,
    market: str = "EUR",
    weeks: int = 52,
) -> dict[str, Any]:
    """Fetch weekly historical COT data for a specific market.

    Args:
        fetcher: Shared HTTP fetcher.
        market: Market symbol (e.g. "EUR", "GOLD", "WTI").
        weeks: Number of weekly historical records to retrieve (default 52).

    Returns:
        Dict with historical records and calculated metrics timeline.
    """
    symbol = market.upper()
    search_term = COT_MARKETS.get(symbol, symbol)

    data = await fetcher.get_json(
        url=_CFTC_SODA_URL,
        source="cftc",
        cache_key=f"cot:history:{symbol}:{weeks}",
        cache_ttl=3600,
        params={
            "$limit": str(weeks),
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$where": f"upper(market_and_exchange_names) like '%{search_term.upper()}%'",
        },
    )

    history = []
    if data and isinstance(data, list):
        for idx in range(len(data)):
            slice_data = data[idx:]
            m = _calculate_metrics(slice_data)
            if m:
                history.append(m)

    return {
        "market": symbol,
        "name": search_term,
        "weeks_requested": weeks,
        "records_count": len(history),
        "history": history,
        "source": "cftc-soda",
        "timestamp": _utc_now_iso(),
    }
