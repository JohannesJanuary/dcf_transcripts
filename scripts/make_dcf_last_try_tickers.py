"""
Build a final DCF-only ticker list using all local evidence collected so far.

The list is not random. It merges:
- companies already confirmed with transcript rows
- priority/untried companies from the S&P 500 universe
- targeted high-yield companies
- status evidence from previous DCF runs

Likely blocked tickers are kept at the back rather than discarded, so this can
serve as a last broad DCF attempt without wasting the early part of the run.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


def normalize_ticker(value: str) -> str:
    return value.strip().upper().replace(".", "-")


def read_text_tickers(path: Path) -> list[str]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8-sig")
    tickers: list[str] = []
    seen: set[str] = set()
    for value in re.split(r"[\s,]+", raw):
        ticker = normalize_ticker(value)
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


def read_csv_tickers(path: Path) -> list[str]:
    if not path.exists():
        return []
    tickers: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = normalize_ticker(row.get("Ticker", ""))
            if ticker and ticker not in seen:
                seen.add(ticker)
                tickers.append(ticker)
    return tickers


def read_data_counts(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = normalize_ticker(row.get("Ticker", ""))
            if ticker:
                counts[ticker] += 1
    return counts


def read_status_counts(path: Path) -> dict[str, Counter[str]]:
    statuses: dict[str, Counter[str]] = defaultdict(Counter)
    if not path.exists():
        return statuses
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = normalize_ticker(row.get("Ticker", ""))
            status = (row.get("Status") or "").strip()
            if ticker and status:
                statuses[ticker][status] += 1
    return statuses


def rank_ticker(
    ticker: str,
    original_order: int,
    data_counts: Counter[str],
    statuses: dict[str, Counter[str]],
    high_yield: set[str],
    priority_order: dict[str, int],
) -> tuple[int, int, int]:
    status_counts = statuses.get(ticker, Counter())
    data_rows = data_counts[ticker]
    blocked = sum(count for status, count in status_counts.items() if "403" in status)
    skipped = status_counts.get("skipped_after_repeated_403", 0)
    ok = status_counts.get("ok", 0)
    empty = status_counts.get("empty", 0)
    errors = sum(count for status, count in status_counts.items() if status.startswith("error:"))

    if data_rows:
        bucket = 0
    elif not status_counts:
        bucket = 1
    elif ticker in high_yield and blocked < 4:
        bucket = 2
    elif ok or empty or errors:
        bucket = 3
    elif blocked < 3 and not skipped:
        bucket = 4
    else:
        bucket = 5

    bonus = 0 if ticker in high_yield else 1
    priority_position = priority_order.get(ticker, original_order)
    return (bucket, bonus, priority_position)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default="dcf_transcripts_browser_tickers.csv")
    parser.add_argument("--priority", default="dcf_priority_tickers.txt")
    parser.add_argument("--high-yield", default="dcf_high_yield_tickers.txt")
    parser.add_argument("--data", default="dcf_transcripts_browser_2022_2025.csv")
    parser.add_argument("--status", default="dcf_transcripts_browser_status.csv")
    parser.add_argument("--output", default="dcf_last_try_tickers.txt")
    parser.add_argument("--report", default="dcf_last_try_tickers_report.csv")
    parser.add_argument("--limit", type=int, default=505)
    args = parser.parse_args()

    base = read_csv_tickers(Path(args.tickers))
    priority = read_text_tickers(Path(args.priority))
    high_yield_list = read_text_tickers(Path(args.high_yield))
    data_counts = read_data_counts(Path(args.data))
    statuses = read_status_counts(Path(args.status))

    merged: list[str] = []
    seen: set[str] = set()
    for source in (list(data_counts), high_yield_list, priority, base):
        for ticker in source:
            if ticker and ticker not in seen:
                seen.add(ticker)
                merged.append(ticker)

    priority_order = {ticker: index for index, ticker in enumerate(priority)}
    high_yield = set(high_yield_list)
    ordered = sorted(
        enumerate(merged),
        key=lambda pair: rank_ticker(pair[1], pair[0], data_counts, statuses, high_yield, priority_order),
    )
    selected = [ticker for _, ticker in ordered[: args.limit]]

    Path(args.output).write_text("\n".join(selected) + "\n", encoding="utf-8")

    with Path(args.report).open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "Rank",
            "Ticker",
            "Data Rows",
            "Status Rows",
            "OK Pages",
            "403 Pages",
            "Skipped After 403",
            "High Yield",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rank, ticker in enumerate(selected, start=1):
            status_counts = statuses.get(ticker, Counter())
            writer.writerow(
                {
                    "Rank": rank,
                    "Ticker": ticker,
                    "Data Rows": data_counts[ticker],
                    "Status Rows": sum(status_counts.values()),
                    "OK Pages": status_counts.get("ok", 0),
                    "403 Pages": sum(count for status, count in status_counts.items() if "403" in status),
                    "Skipped After 403": status_counts.get("skipped_after_repeated_403", 0),
                    "High Yield": ticker in high_yield,
                }
            )

    print(f"wrote {len(selected)} tickers to {args.output}")
    print(f"report={args.report}")
    print(f"confirmed_with_rows={sum(1 for ticker in selected if data_counts[ticker])}")
    print(f"untried={sum(1 for ticker in selected if not statuses.get(ticker) and not data_counts[ticker])}")
    print(f"high_yield={sum(1 for ticker in selected if ticker in high_yield)}")


if __name__ == "__main__":
    main()
