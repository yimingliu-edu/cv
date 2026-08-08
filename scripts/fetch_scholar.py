#!/usr/bin/env python3
"""
Fetch Yiming Liu's Google Scholar profile and write to data/scholar.json.

Strategy (in order):
  1. Direct HTTP scrape with realistic browser headers + retry/backoff.
  2. OpenAlex API as a fallback (slower update but stable).
  3. If everything fails, keep the existing data/scholar.json untouched so the
     site keeps showing the last known values.

Outputs data/scholar.json with this shape:
{
  "citations": int,
  "h_index": int,
  "i10_index": int,
  "yearly": {"2022": 2, "2023": 5, ...},
  "publications": [{"title": "...", "cited_by": 12, "year": 2023, "url": "..."}, ...],
  "profile_url": "https://scholar.google.com/citations?user=lmbr2XYAAAAJ&hl=en",
  "last_updated": "2026-08-08T08:00:00+08:00",
  "source": "google_scholar" | "openalex" | "cache"
}
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

# ---------- Config -----------------------------------------------------------

SCHOLAR_USER_ID = "lmbr2XYAAAAJ"
SCHOLAR_URL = f"https://scholar.google.com/citations?user={SCHOLAR_USER_ID}&hl=en"

# OpenAlex author ID for the same person. Hard-coded after resolving via
# title-search ("Temporal learning analytics to explore traces of SRL
# behaviors...") so the fallback is reliable regardless of name disambiguation.
OPENALEX_AUTHOR_ID = "A5100449929"
OPENALEX_AUTHOR_URL = f"https://api.openalex.org/authors/{OPENALEX_AUTHOR_ID}"

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "scholar.json"

# Hong Kong time = UTC+8. The workflow runs at 00:00 UTC == 08:00 Hong Kong.
HONGKONG_TZ = timezone(timedelta(hours=8))

USER_AGENTS = [
    # A small pool of recent, real desktop UAs.
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# OpenAlex requires a contact email in the User-Agent or via `mailto=` query
# param. We pass it as a query param so we can keep the browser-looking UA
# for Google Scholar on the same code path.
OPENALEX_CONTACT = "eduliuym@connect.hku.hk"

# ---------- Helpers ----------------------------------------------------------

def hongkong_now_iso() -> str:
    return datetime.now(HONGKONG_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_existing() -> dict[str, Any] | None:
    if OUTPUT_PATH.exists():
        try:
            return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_json(payload: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[ok] wrote {OUTPUT_PATH}")


def make_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            # Note: do NOT advertise "br" (Brotli). The `requests` library
            # doesn't ship with a Brotli decoder; the server will then send
            # raw Brotli which `requests` won't auto-decompress.
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
    )
    return sess


def get_with_retry(
    url: str,
    *,
    max_attempts: int = 4,
    base_delay: float = 3.0,
    params: dict[str, Any] | None = None,
) -> requests.Response | None:
    """GET with exponential backoff. Returns None on persistent failure."""
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        sess = make_session()
        try:
            r = sess.get(url, params=params, timeout=30, allow_redirects=True)
            if r.status_code == 200 and "captcha" not in r.text.lower():
                return r
            if r.status_code in (429, 503):
                # Rate limited. Back off aggressively.
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 2)
                print(f"[warn] HTTP {r.status_code}, sleeping {delay:.1f}s (attempt {attempt}/{max_attempts})")
                time.sleep(delay)
                continue
            # Other 4xx/5xx
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"[warn] HTTP {r.status_code}, sleeping {delay:.1f}s (attempt {attempt}/{max_attempts})")
            time.sleep(delay)
        except requests.RequestException as e:
            last_exc = e
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"[warn] {type(e).__name__}: {e}, sleeping {delay:.1f}s (attempt {attempt}/{max_attempts})")
            time.sleep(delay)
    if last_exc:
        print(f"[error] all attempts failed for {url}: {last_exc}")
    else:
        print(f"[error] all attempts failed for {url}")
    return None


# ---------- Google Scholar parser --------------------------------------------

def _num(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def parse_scholar(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    # Citation table: gsc_rsb_std contains rows like Citations / h-index / i10-index
    # and the "Since YYYY" column. We only use the "All" column (index 0).
    metrics = {"citations": 0, "h_index": 0, "i10_index": 0}
    rows = soup.select("table.gsc_rsb_std tr")
    # The table is actually two side-by-side tables (All / Since YYYY).
    # Each has 3 rows in the same order.
    for table in soup.select("table.gsc_rsb_std"):
        cells = [_num(td.get_text()) for td in table.select("td")]
        if len(cells) >= 3:
            # Only the first table (the "All" column)
            if metrics["citations"] == 0:
                metrics["citations"], metrics["h_index"], metrics["i10_index"] = cells[0], cells[1], cells[2]

    # Yearly histogram
    yearly: dict[str, int] = {}
    for bar in soup.select("div.gsc_md_hist_b"):
        year_el = bar.find("span", class_="gsc_md_hist_t")
        # Each bar has nested spans with year + count.
        # Older GS markup: <span class="gsc_md_hist_t">2024</span> + style width
        # We need to read the inline count — it's set as style width but the
        # count is also exposed as a sibling span in modern markup.
        count_el = bar.find("span", class_="gsc_md_hist_c") or bar.find("a")
        if year_el and count_el:
            y = year_el.get_text(strip=True)
            c = _num(count_el.get_text())
            if y.isdigit() and c >= 0:
                yearly[y] = c

    # Publications (rows in the user profile table)
    publications: list[dict[str, Any]] = []
    for row in soup.select("tr.gsc_a_tr"):
        a = row.select_one("a.gsc_a_at")
        cited = row.select_one("td.gsc_a_c")
        year_td = row.select_one("td.gsc_a_y")
        if not a:
            continue
        publications.append(
            {
                "title": a.get_text(strip=True),
                "url": urljoin(SCHOLAR_URL, a.get("href", "")),
                "cited_by": _num(cited.get_text()) if cited else 0,
                "year": int(year_td.get_text(strip=True) or 0) if year_td else 0,
            }
        )

    return {
        "metrics": metrics,
        "yearly": yearly,
        "publications": publications,
    }


def fetch_google_scholar() -> dict[str, Any] | None:
    """Scrape Google Scholar. Returns parsed data or None on failure."""
    print("[info] trying Google Scholar...")
    r = get_with_retry(SCHOLAR_URL)
    if r is None:
        return None
    try:
        data = parse_scholar(r.text)
    except Exception as e:
        print(f"[error] parse_scholar failed: {e}")
        return None

    if data["metrics"]["citations"] == 0 and data["metrics"]["h_index"] == 0:
        print("[warn] parsed zero metrics — likely got a CAPTCHA / error page")
        return None

    print(
        f"[ok] google scholar: citations={data['metrics']['citations']} "
        f"h={data['metrics']['h_index']} i10={data['metrics']['i10_index']} "
        f"publications={len(data['publications'])}"
    )
    return data


# ---------- OpenAlex fallback ------------------------------------------------

def fetch_openalex() -> dict[str, Any] | None:
    """Fallback: use OpenAlex to derive approximate scholar metrics."""
    print(f"[info] trying OpenAlex fallback (id={OPENALEX_AUTHOR_ID})...")
    r = get_with_retry(
        OPENALEX_AUTHOR_URL,
        params={"mailto": OPENALEX_CONTACT},
        max_attempts=3,
        base_delay=2.0,
    )
    if r is None:
        return None
    try:
        author = r.json()
    except ValueError:
        return None
    if not author or "id" not in author:
        print("[warn] OpenAlex: empty / invalid author response")
        return None

    summary = author.get("summary_stats") or {}
    cited_by_count = author.get("cited_by_count", 0)
    h_index = summary.get("h_index")
    i10_index = summary.get("i10_index")
    works_count = author.get("works_count", 0)

    print(
        f"[ok] openalex match: {author.get('display_name')} "
        f"(works={works_count}, cited_by={cited_by_count}, h={h_index}, i10={i10_index})"
    )
    return {
        "metrics": {
            "citations": int(cited_by_count or 0),
            "h_index": int(h_index or 0),
            "i10_index": int(i10_index or 0),
        },
        "yearly": {},
        "publications": [],
        "extra": {
            "works_count": works_count,
            "openalex_id": author.get("id"),
        },
    }


# ---------- Main -------------------------------------------------------------

def build_payload(source: str, parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "citations": parsed["metrics"]["citations"],
        "h_index": parsed["metrics"]["h_index"],
        "i10_index": parsed["metrics"]["i10_index"],
        "yearly": parsed.get("yearly", {}),
        "publications": parsed.get("publications", []),
        "profile_url": SCHOLAR_URL,
        "last_updated": hongkong_now_iso(),
        "source": source,
        "extra": parsed.get("extra", {}),
    }


def main() -> int:
    existing = load_existing()

    # 1. Google Scholar
    parsed = fetch_google_scholar()
    if parsed and parsed["metrics"]["citations"] > 0:
        save_json(build_payload("google_scholar", parsed))
        return 0

    # 2. OpenAlex fallback — only update h/i10, never overwrite GS citations
    parsed = fetch_openalex()
    if parsed and parsed["metrics"]["citations"] > 0:
        payload = build_payload("openalex", parsed)
        # Preserve historical yearly/publications from previous runs so the
        # chart doesn't reset to empty.
        if existing:
            payload["yearly"] = existing.get("yearly") or payload["yearly"]
            payload["publications"] = existing.get("publications") or payload["publications"]
            # **Critical**: OpenAlex cited_by_count is consistently higher
            # than Google Scholar (206 vs 180 for this author). Never trust
            # the OA citation number — always keep the last known value.
            if existing.get("citations"):
                oa_before = payload["citations"]
                payload["citations"] = existing["citations"]
                print(
                    f"[info] keeping last known citations={existing['citations']} "
                    f"(OpenAlex says {oa_before})"
                )
        save_json(payload)
        return 0

    # 3. Keep existing
    if existing:
        print("[warn] all sources failed; keeping existing scholar.json")
        # Update the last_updated marker so we know the workflow ran
        existing["last_updated"] = hongkong_now_iso()
        existing["source"] = existing.get("source", "cache") + "+stale"
        save_json(existing)
        return 0

    # 4. Nothing on disk at all — write a placeholder
    print("[error] no data sources worked and no existing file; writing placeholder")
    save_json(
        {
            "citations": 0,
            "h_index": 0,
            "i10_index": 0,
            "yearly": {},
            "publications": [],
            "profile_url": SCHOLAR_URL,
            "last_updated": hongkong_now_iso(),
            "source": "placeholder",
            "extra": {"error": "All sources failed on first run"},
        }
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
