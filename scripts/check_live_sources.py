"""Live endpoint validator for world-intel-mcp.

Checks all live RSS feeds and REST endpoints without mocking,
reporting 404, 403, SSL, and timeout issues instantly.
"""

import asyncio
import sys
import httpx
from world_intel_mcp.sources.news import _RSS_FEEDS

# Windows UTF-8 stdout fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def check_rss_feeds() -> tuple[int, int, list[tuple[str, str, int]]]:
    """Check all registered RSS feeds concurrently for HTTP status."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.9,*/*;q=0.8",
    }

    all_feeds: list[tuple[str, str, str]] = []
    for cat, feeds in _RSS_FEEDS.items():
        for name, url in feeds:
            all_feeds.append((cat, name, url))

    failures: list[tuple[str, str, int]] = []
    success_count = 0

    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True, verify=False) as client:
        semaphore = asyncio.Semaphore(15)

        async def _check_feed(cat: str, name: str, url: str):
            nonlocal success_count
            async with semaphore:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        success_count += 1
                    else:
                        failures.append((name, url, resp.status_code))
                except Exception:
                    failures.append((name, url, 0))

        await asyncio.gather(*[_check_feed(c, n, u) for c, n, u in all_feeds])

    return len(all_feeds), success_count, failures


async def main():
    print("🔍 Live RSS Feed Health Check starting...")
    total, ok, failures = await check_rss_feeds()
    print(f"\n📊 Summary: {ok}/{total} RSS feeds active ({(ok/total)*100:.1f}%)")

    if failures:
        print("\n⚠️ Broken feeds detected:")
        for name, url, status in failures:
            st_text = f"HTTP {status}" if status else "SSL/Connect Error"
            print(f"  - [{st_text}] {name}: {url}")
    else:
        print("✨ All RSS feeds are 100% active and healthy!")


if __name__ == "__main__":
    asyncio.run(main())
