# DCF Earnings Call Transcript Collection

Python toolkit for collecting, cleaning, and documenting earnings call transcript datasets. The project supports company-quarter, speaker-level transcript data for downstream NLP/AI analysis of corporate communication patterns.

## Project Purpose

This repository contains the Python collection workflow and metadata reports for a research project using publicly accessible earnings call transcript pages from DiscountingCashflows.com.

The project builds a speaker-message level dataset of earnings call transcripts for public companies. The dataset is intended for academic analysis of corporate communication, executive language, topic patterns, and AI-assisted text analytics.

## Locked Dataset Snapshot

The locked local dataset was created on **2026-05-26**.

Summary:

- Message rows: **80,350**
- Unique companies: **500**
- Unique company-quarter calls: **1,348**
- Years covered: **2022-2025**

The full transcript CSV is not included in this GitHub package because it contains complete transcript text and should be shared only in line with source-site terms, academic-use requirements, and redistribution permissions.

Local locked dataset filename:

```text
locked_dcf_dataset/dcf_transcripts_LOCKED_2022_2025_2026-05-26.csv
```

## Included Files

```text
scripts/collect_dcf_transcripts_browser_legal.py
scripts/make_dcf_priority_batches.py
scripts/make_dcf_last_try_tickers.py
metadata/dcf_coverage_summary_LOCKED_2026-05-26.csv
metadata/dcf_company_quarter_matrix_LOCKED_2026-05-26.csv
metadata/dcf_locked_dataset_summary_2026-05-26.json
```

## Dataset Structure

The full dataset uses a speaker-message format with columns such as:

- Ticker
- Company
- Year
- Quarter
- Speaker Name
- Message Number
- Message Content
- Source URL
- Collection Date

## Research Notes

The collection process produced both broad coverage and a smaller balanced-panel subset. Coverage varies by quarter because transcript availability and website access differed across companies and time periods.

Useful locked metadata files:

- `metadata/dcf_coverage_summary_LOCKED_2026-05-26.csv`
- `metadata/dcf_company_quarter_matrix_LOCKED_2026-05-26.csv`
- `metadata/dcf_locked_dataset_summary_2026-05-26.json`

## Main Collection Script

The primary script is:

```text
scripts/collect_dcf_transcripts_browser_legal.py
```

Example command pattern:

```powershell
python scripts/collect_dcf_transcripts_browser_legal.py `
  --tickers-file dcf_confirmed_500_tickers.txt `
  --company-limit 500 `
  --start-year 2022 `
  --end-year 2025 `
  --quarters 1,2,3,4 `
  --min-delay 16 `
  --wait-after-load 4 `
  --output dcf_transcripts_browser_2022_2025.csv `
  --page-status dcf_transcripts_browser_status.csv `
  --tickers-output dcf_transcripts_browser_tickers.csv
```

## Ethical Use

This project is designed for academic research. Users should respect website terms, rate limits, robots policies where applicable, and copyright or redistribution restrictions for transcript text.
