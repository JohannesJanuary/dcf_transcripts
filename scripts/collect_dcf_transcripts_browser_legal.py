"""
Legally cautious browser-rendered collector for Discounting Cash Flows
earnings call transcripts.

Purpose
-------
Build a research CSV with speaker-level earnings call transcript rows from
publicly accessible Discounting Cash Flows transcript pages.

This script is deliberately conservative:
- It uses a normal browser renderer because the site is JavaScript-driven.
- It does not bypass login walls, 403 responses, CAPTCHAs, or paywalls.
- It respects configurable request caps below DCF's published fair-use limits.
- It checkpoints every page so the run can continue over several days.

DCF fair-use limits observed from their Terms page on 2026-05-20:
- Unauthenticated: 480 requests/day, 120/hour, 60/minute.
- Authenticated: 960 requests/day, 240/hour, 60/minute.

Suggested research run:
    python collect_dcf_transcripts_browser_legal.py --company-limit 505 \
        --start-year 2022 --end-year 2025 \
        --daily-page-cap 430 --hourly-page-cap 100 --min-delay 25 \
        --output dcf_transcripts_browser_2022_2025.csv

Requirements:
    pip install playwright
    python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DCF_BASE = "https://discountingcashflows.com"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

DEFAULT_OUTPUT = "dcf_transcripts_browser_2022_2025.csv"
DEFAULT_PAGE_STATUS = "dcf_transcripts_browser_page_status.csv"
DEFAULT_TICKERS = "dcf_transcripts_browser_tickers.csv"
DEFAULT_START_YEAR = 2022
DEFAULT_END_YEAR = 2025
DEFAULT_COMPANY_LIMIT = 505

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


@dataclass(frozen=True)
class TargetPage:
    ticker: str
    company: str
    year: int
    quarter: int
    url: str


class WikiTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_table = False
        self._table_depth = 0
        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table" and "wikitable" in (attrs_dict.get("class") or "") and not self._in_table:
            self._in_table = True
            self._table_depth = 1
            return
        if self._in_table and tag == "table":
            self._table_depth += 1
        if not self._in_table:
            return
        if tag == "tr":
            self._in_row = True
            self._current_row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if not self._in_table:
            return
        if tag in {"td", "th"} and self._in_cell:
            self._current_row.append(clean_text("".join(self._current_cell)))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._current_row:
                self.rows.append(self._current_row)
            self._in_row = False
        elif tag == "table":
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=45) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_sp500(company_limit: int) -> list[tuple[str, str]]:
    html = fetch_text(SP500_URL)
    parser = WikiTableParser()
    parser.feed(html)
    companies: list[tuple[str, str]] = []
    for row in parser.rows:
        if len(row) < 2 or row[0].lower() == "symbol":
            continue
        ticker = normalize_ticker(row[0])
        company = clean_text(row[1])
        if re.fullmatch(r"[A-Z][A-Z0-9-]{0,9}", ticker):
            companies.append((ticker, company))
        if len(companies) >= company_limit:
            break
    return companies


def parse_tickers_arg(value: str, company_limit: int | None) -> list[tuple[str, str]]:
    companies = [(normalize_ticker(x), normalize_ticker(x)) for x in value.split(",") if x.strip()]
    return companies[:company_limit] if company_limit else companies


def read_tickers_file(path: Path, company_limit: int | None) -> list[tuple[str, str]]:
    raw = path.read_text(encoding="utf-8-sig")
    companies = [(normalize_ticker(x), normalize_ticker(x)) for x in re.split(r"[\s,]+", raw) if x.strip()]
    return companies[:company_limit] if company_limit else companies


def build_companies(args: argparse.Namespace) -> list[tuple[str, str]]:
    if args.tickers:
        companies = parse_tickers_arg(args.tickers, args.company_limit)
    elif args.tickers_file:
        companies = read_tickers_file(Path(args.tickers_file), args.company_limit)
    else:
        companies = fetch_sp500(args.company_limit)

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ticker, company in companies:
        if ticker and ticker not in seen:
            seen.add(ticker)
            deduped.append((ticker, company or ticker))
    return deduped


def build_targets(
    companies: Iterable[tuple[str, str]],
    start_year: int,
    end_year: int,
    quarters: Iterable[int],
    target_order: str,
) -> list[TargetPage]:
    company_list = list(companies)
    quarter_list = list(quarters)
    targets: list[TargetPage] = []
    if target_order == "round-robin":
        for year in range(start_year, end_year + 1):
            for quarter in quarter_list:
                for ticker, company in company_list:
                    targets.append(
                        TargetPage(
                            ticker=ticker,
                            company=company,
                            year=year,
                            quarter=quarter,
                            url=f"{DCF_BASE}/company/{ticker}/transcripts/{year}/{quarter}/",
                        )
                    )
    else:
        for ticker, company in company_list:
            for year in range(start_year, end_year + 1):
                for quarter in quarter_list:
                    targets.append(
                        TargetPage(
                            ticker=ticker,
                            company=company,
                            year=year,
                            quarter=quarter,
                            url=f"{DCF_BASE}/company/{ticker}/transcripts/{year}/{quarter}/",
                        )
                    )
    return targets


def parse_quarters(value: str) -> list[int]:
    quarters: list[int] = []
    for raw_part in value.split(","):
        part = raw_part.strip().upper().removeprefix("Q")
        if not part:
            continue
        try:
            quarter = int(part)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid quarter: {raw_part!r}") from exc
        if quarter < 1 or quarter > 4:
            raise argparse.ArgumentTypeError(f"Quarter must be 1, 2, 3, or 4: {raw_part!r}")
        if quarter not in quarters:
            quarters.append(quarter)
    if not quarters:
        raise argparse.ArgumentTypeError("At least one quarter is required")
    return quarters


def append_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def load_completed(status_path: Path, retry_failed: bool) -> set[str]:
    if not status_path.exists():
        return set()
    completed: set[str] = set()
    with status_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            url = row.get("Source URL", "")
            status = row.get("Status", "")
            if not url:
                continue
            if status == "ok" or (status and not retry_failed):
                completed.add(url)
    return completed


def current_utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def visible_transcript_text(page_text: str) -> str:
    text = unescape(page_text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def is_probable_speaker(line: str) -> bool:
    if not (2 <= len(line) <= 90):
        return False
    lowered = line.lower()
    blocked = {
        "contents",
        "prepared remarks",
        "question-and-answer session",
        "questions and answers",
        "earnings call transcript",
        "transcript",
        "ai insights",
        "loading data",
        "select transcript",
        "javascript is disabled",
    }
    if lowered in blocked:
        return False
    if line.endswith((".", ",", ";", ":")):
        return False
    if len(line.split()) > 9:
        return False
    return bool(re.search(r"[A-Za-z]", line))


def parse_messages_from_text(page_text: str) -> list[tuple[str, str]]:
    lines = [clean_text(x) for x in visible_transcript_text(page_text).splitlines() if clean_text(x)]
    if len(" ".join(lines)) < 800:
        return []

    start_index = 0
    for i, line in enumerate(lines):
        if line.lower() in {"operator", "prepared remarks"}:
            start_index = i
            break
        if re.search(r"\b(operator|prepared remarks|question-and-answer session)\b", line, re.I):
            start_index = i
            break
    lines = lines[start_index:]

    messages: list[tuple[str, str]] = []
    current_speaker: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if current_speaker and buffer:
            content = clean_text(" ".join(buffer))
            if len(content) > 40:
                messages.append((current_speaker, content))
        buffer = []

    for line in lines:
        if is_probable_speaker(line):
            if current_speaker is None:
                current_speaker = line
                continue
            if buffer:
                flush()
                current_speaker = line
                continue
        if current_speaker:
            buffer.append(line)
    flush()

    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for speaker, content in messages:
        key = (speaker.lower(), content[:180].lower())
        if key not in seen:
            seen.add(key)
            deduped.append((speaker, content))
    return deduped


async def safe_page_text(page, target: TargetPage, wait_seconds: float) -> tuple[str, str]:
    try:
        response = await page.goto(target.url, wait_until="domcontentloaded", timeout=60_000)
        status_code = response.status if response else 0
        if status_code in {401, 402, 403, 404}:
            return "", f"blocked_or_missing:{status_code}"
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await page.wait_for_timeout(int(wait_seconds * 1000))
        text = ""
        transcript = page.locator("#transcriptsContent")
        if await transcript.count():
            text = await transcript.inner_text(timeout=10_000)
        if not text:
            # Remove style/script clutter before using the whole body as fallback.
            text = await page.evaluate(
                """
                () => {
                    document.querySelectorAll('script,style,svg,nav,footer,header,dialog')
                        .forEach((el) => el.remove());
                    return document.body ? document.body.innerText : '';
                }
                """
            )
        text = text or ""
        if "javascript is disabled" in text.lower() and len(text) < 1500:
            return text, "js_placeholder"
        return text, "loaded"
    except Exception as exc:
        return "", f"error:{type(exc).__name__}:{exc}"


async def run_async(args: argparse.Namespace) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise SystemExit(
            "Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
        )

    output_path = Path(args.output)
    status_path = Path(args.page_status)
    tickers_path = Path(args.tickers_output)

    row_fields = [
        "Company",
        "Ticker",
        "Year",
        "Quarter",
        "Speaker Name",
        "Message Number",
        "Message Content",
        "Source URL",
        "Collection Date",
    ]
    status_fields = ["Ticker", "Company", "Year", "Quarter", "Status", "Rows", "Source URL", "Collection Date"]
    ticker_fields = ["Ticker", "Company"]

    companies = build_companies(args)
    append_csv(tickers_path, ticker_fields, [{"Ticker": t, "Company": c} for t, c in companies])

    targets = build_targets(companies, args.start_year, args.end_year, args.quarters, args.target_order)
    completed = load_completed(status_path, retry_failed=args.retry_failed)
    targets = [target for target in targets if target.url not in completed]
    if args.max_pages:
        targets = targets[: args.max_pages]

    print(f"Companies: {len(companies)}")
    print(f"Remaining target pages: {len(targets)}")

    day_started = current_utc_day()
    daily_count = 0
    hourly_window_started = time.monotonic()
    hourly_count = 0
    successful_companies: set[str] = set()
    consecutive_blocked_by_ticker: dict[str, int] = {}
    skipped_tickers: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        for index, target in enumerate(targets, start=1):
            if target.ticker in skipped_tickers:
                collection_date = datetime.now(timezone.utc).isoformat()
                append_csv(
                    status_path,
                    status_fields,
                    [
                        {
                            "Ticker": target.ticker,
                            "Company": target.company,
                            "Year": target.year,
                            "Quarter": f"Q{target.quarter}",
                            "Status": "skipped_after_repeated_403",
                            "Rows": 0,
                            "Source URL": target.url,
                            "Collection Date": collection_date,
                        }
                    ],
                )
                continue

            if current_utc_day() != day_started:
                day_started = current_utc_day()
                daily_count = 0
            if daily_count >= args.daily_page_cap:
                print(f"Reached daily page cap ({args.daily_page_cap}). Stop and resume tomorrow.")
                break

            elapsed_hour = time.monotonic() - hourly_window_started
            if elapsed_hour >= 3600:
                hourly_window_started = time.monotonic()
                hourly_count = 0
            if hourly_count >= args.hourly_page_cap:
                sleep_for = 3600 - elapsed_hour + 5
                print(f"Reached hourly cap. Sleeping {sleep_for:.0f}s.")
                await asyncio.sleep(max(5, sleep_for))
                hourly_window_started = time.monotonic()
                hourly_count = 0

            await asyncio.sleep(args.min_delay)
            page_text, load_status = await safe_page_text(page, target, args.wait_after_load)
            daily_count += 1
            hourly_count += 1

            messages = parse_messages_from_text(page_text) if load_status == "loaded" else []
            status = "ok" if messages else load_status if load_status != "loaded" else "empty"
            collection_date = datetime.now(timezone.utc).isoformat()

            if status == "blocked_or_missing:403":
                consecutive_blocked_by_ticker[target.ticker] = consecutive_blocked_by_ticker.get(target.ticker, 0) + 1
                if consecutive_blocked_by_ticker[target.ticker] >= args.max_consecutive_403:
                    skipped_tickers.add(target.ticker)
            elif status == "ok":
                consecutive_blocked_by_ticker[target.ticker] = 0

            rows = [
                {
                    "Company": target.company,
                    "Ticker": target.ticker,
                    "Year": target.year,
                    "Quarter": f"Q{target.quarter}",
                    "Speaker Name": speaker,
                    "Message Number": message_number,
                    "Message Content": content,
                    "Source URL": target.url,
                    "Collection Date": collection_date,
                }
                for message_number, (speaker, content) in enumerate(messages, start=1)
            ]
            if rows:
                append_csv(output_path, row_fields, rows)
                successful_companies.add(target.ticker)

            append_csv(
                status_path,
                status_fields,
                [
                    {
                        "Ticker": target.ticker,
                        "Company": target.company,
                        "Year": target.year,
                        "Quarter": f"Q{target.quarter}",
                        "Status": status,
                        "Rows": len(rows),
                        "Source URL": target.url,
                        "Collection Date": collection_date,
                    }
                ],
            )

            print(
                f"[{index}/{len(targets)}] {target.ticker} {target.year} Q{target.quarter}: "
                f"{status}, rows={len(rows)}, successful_companies={len(successful_companies)}",
                flush=True,
            )

            if args.stop_after_successful_companies and len(successful_companies) >= args.stop_after_successful_companies:
                print("Reached successful-company target.")
                break

        await context.close()
        await browser.close()

    print(f"Output: {output_path.resolve()}")
    print(f"Status: {status_path.resolve()}")
    print(f"Ticker universe: {tickers_path.resolve()}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=None)
    parser.add_argument("--tickers-file", default=None)
    parser.add_argument("--company-limit", type=int, default=DEFAULT_COMPANY_LIMIT)
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument(
        "--quarters",
        type=parse_quarters,
        default=[1, 2, 3, 4],
        help="Comma-separated quarters to collect, for example 2 or 1,2,3,4.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--page-status", default=DEFAULT_PAGE_STATUS)
    parser.add_argument("--tickers-output", default=DEFAULT_TICKERS)
    parser.add_argument("--daily-page-cap", type=int, default=430)
    parser.add_argument("--hourly-page-cap", type=int, default=100)
    parser.add_argument("--min-delay", type=float, default=25.0)
    parser.add_argument("--wait-after-load", type=float, default=4.0)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--stop-after-successful-companies", type=int, default=None)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--target-order",
        choices=["company", "round-robin"],
        default="company",
        help=(
            "company collects all quarters for one ticker before moving on; "
            "round-robin collects the same quarter across many tickers first, "
            "which improves company breadth early in the run."
        ),
    )
    parser.add_argument(
        "--max-consecutive-403",
        type=int,
        default=3,
        help=(
            "Skip the rest of a ticker for this run after this many consecutive "
            "403 pages. Skipped pages are logged and can be retried later with --retry-failed."
        ),
    )
    return parser


def main() -> None:
    asyncio.run(run_async(build_parser().parse_args()))


if __name__ == "__main__":
    main()
