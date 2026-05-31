"""
Create prioritized ticker batches for the DCF transcript collector.

This helper does not contact Discounting Cash Flows. It reads the local
checkpoint/data files and writes a ticker list that helps the next collector
run spend time on companies that are more likely to add new company coverage.

Priority order:
1. untried companies
2. companies with non-403/no-data statuses
3. companies that already have some transcript rows
4. companies that appear repeatedly blocked
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def read_tickers(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        ticker = (row.get("Ticker") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        cleaned.append({"Ticker": ticker, "Company": (row.get("Company") or ticker).strip()})
    return cleaned


def read_data_counts(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get("Ticker") or "").strip().upper()
            if ticker:
                counts[ticker] += 1
    return counts


def read_statuses(path: Path) -> dict[str, Counter[str]]:
    statuses: dict[str, Counter[str]] = defaultdict(Counter)
    if not path.exists():
        return statuses
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get("Ticker") or "").strip().upper()
            status = (row.get("Status") or "").strip()
            if ticker and status:
                statuses[ticker][status] += 1
    return statuses


def category_for(ticker: str, data_rows: int, statuses: Counter[str]) -> tuple[int, str]:
    total_statuses = sum(statuses.values())
    blocked = sum(count for status, count in statuses.items() if "403" in status)
    skipped = statuses.get("skipped_after_repeated_403", 0)
    ok = statuses.get("ok", 0)

    if total_statuses == 0 and data_rows == 0:
        return 0, "untried"
    if data_rows == 0 and skipped == 0 and blocked < 3:
        return 1, "retry_or_unclear_no_data"
    if data_rows > 0:
        return 2, "already_has_data"
    if ok > 0:
        return 2, "status_ok_but_no_rows"
    return 3, "likely_blocked"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default="dcf_transcripts_browser_tickers.csv")
    parser.add_argument("--data", default="dcf_transcripts_browser_2022_2025.csv")
    parser.add_argument("--status", default="dcf_transcripts_browser_status.csv")
    parser.add_argument("--output", default="dcf_priority_tickers.txt")
    parser.add_argument("--report", default="dcf_priority_tickers_report.csv")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    tickers = read_tickers(Path(args.tickers))
    data_counts = read_data_counts(Path(args.data))
    statuses = read_statuses(Path(args.status))

    report_rows: list[dict[str, object]] = []
    for index, row in enumerate(tickers):
        ticker = row["Ticker"]
        status_counts = statuses.get(ticker, Counter())
        priority, category = category_for(ticker, data_counts[ticker], status_counts)
        report_rows.append(
            {
                "Priority": priority,
                "Original Order": index + 1,
                "Ticker": ticker,
                "Company": row["Company"],
                "Category": category,
                "Data Rows": data_counts[ticker],
                "Status Rows": sum(status_counts.values()),
                "OK Pages": status_counts.get("ok", 0),
                "403 Pages": sum(count for status, count in status_counts.items() if "403" in status),
                "Skipped After 403": status_counts.get("skipped_after_repeated_403", 0),
            }
        )

    report_rows.sort(key=lambda row: (row["Priority"], row["Original Order"]))
    if args.limit is not None:
        report_rows = report_rows[: args.limit]

    output_path = Path(args.output)
    output_path.write_text(
        "\n".join(str(row["Ticker"]) for row in report_rows) + "\n",
        encoding="utf-8",
    )

    report_path = Path(args.report)
    with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "Priority",
            "Original Order",
            "Ticker",
            "Company",
            "Category",
            "Data Rows",
            "Status Rows",
            "OK Pages",
            "403 Pages",
            "Skipped After 403",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)

    counts = Counter(str(row["Category"]) for row in report_rows)
    print(f"wrote {len(report_rows)} tickers to {output_path}")
    print(f"wrote report to {report_path}")
    for category, count in sorted(counts.items()):
        print(f"{category}: {count}")


if __name__ == "__main__":
    main()
