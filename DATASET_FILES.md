# Dataset File Guide

## Final Full Dataset

The final locked full dataset is:

```text
locked_dcf_dataset/dcf_transcripts_LOCKED_2022_2025_2026-05-26.csv
```

It contains:

- 80,350 speaker-message rows
- 500 companies
- 1,348 unique company-quarter calls
- Earnings call transcripts from 2022-2025

## Recommended GitHub Upload

Upload the code and metadata reports, not the full transcript CSV, unless redistribution is approved.

Recommended files for GitHub:

- `README.md`
- `requirements.txt`
- `scripts/collect_dcf_transcripts_browser_legal.py`
- `scripts/make_dcf_priority_batches.py`
- `scripts/make_dcf_last_try_tickers.py`
- `metadata/dcf_coverage_summary_LOCKED_2026-05-26.csv`
- `metadata/dcf_company_quarter_matrix_LOCKED_2026-05-26.csv`
- `metadata/dcf_locked_dataset_summary_2026-05-26.json`

## Private Sharing

For professor review, share the full locked dataset privately through OneDrive, Google Drive, Quinnipiac storage, or a private GitHub Release if redistribution permissions are clear.
