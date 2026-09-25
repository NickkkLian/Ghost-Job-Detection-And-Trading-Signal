# Data

The raw data used in this project is proprietary and is **not included** in this
repository. This file describes what data is needed, how it is structured, and how
to obtain access.

---

## What Data Is Used

The notebook `notebooks/Ghost_Job_Pipeline_v2.ipynb` reads three Revelio Labs tables, each a folder of parquet
files (cell 3 sets `DATA_DIR`; Revelio spells the postings folder `positings`):

| Folder under `DATA_DIR` | What the notebook reads from it |
|---|---|
| `revelio_company_ref/` | `rcid`, `company`, `ticker`, `exchange_name`, `naics_code` — US-listed firms with a ticker |
| `revelio_individual_position/` | `rcid`, `user_id`, `startdate`, `enddate` — start and end dates of individual positions |
| `revelio_positings_unified_individual/` | `job_id`, `rcid`, `salary`, `post_date`, `remove_date`, `remote_type`, `expected_hires`, `job_category`, `role_k50` |

**Coverage in the report:** 310,821 postings · 2,919 US public firms · 2009–2024 · 1,017 firms with ≥ 3 postings a quarter.

### What the notebook builds from them

Everything below is computed, not downloaded. The notebook writes it to `OUTPUT_DIR` (cell 3):

| File | Built in | Contents |
|---|---|---|
| `firm_quarter_features.parquet` | cells 8–16 | per firm-quarter: 10 posting features, `headcount` (running sum of starts minus ends from the positions table), `log_headcount`, `headcount_growth_4q`, `naics_int`, and the target `actual_inflows_next_q` |
| `model_predictions.parquet` | cell 26 | XGBoost `predicted_inflows` for the validation and test firms |
| `company_measures.parquet` | cell 27 | per company: predicted and actual fill rate |
| `ghost_scores_fq.parquet` | cell 29 | per firm-quarter `ghost_score` and the company-level `is_ghost` flag — **the file the backtest scripts read** |

### What the backtest scripts need

`scripts/ghost_backtest_v2.py` and `scripts/ghost_concentration_compare_3.py` read one file, `ghost_scores_fq.parquet`,
with at least `ticker`, `quarter` (`YYYY-QN`) and `ghost_score`; `is_ghost` enables the Threshold strategy and
`company` enables the ticker identity check. Prices come from Yahoo Finance.

### No licence? Use the synthetic data

```bash
python scripts/make_synthetic.py
python scripts/ghost_backtest_v2.py --synthetic
```

`make_synthetic.py` writes `data/synthetic/` (ignored by git): a score file in the notebook's output schema for
200 made-up firms (`SYN001`…, companies marked "(synthetic)"), made-up daily prices with the benchmark `SYNMKT`,
and a `manifest.json`. `--synthetic` reads those instead of downloading anything. The numbers it prints say nothing
about ghost postings; they show that the pipeline runs. `python scripts/check.py` generates fresh synthetic data in a
temporary folder, runs both scripts on it and tests that the backtester cannot see scores before they are published.

---

## How to Obtain Access

Revelio Labs data is available through two channels depending on your institution.

### Option 1 — WRDS (Recommended for most universities)

Revelio Labs is available on the
[Wharton Research Data Services (WRDS)](https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/revelio-labs/)
platform. Many universities hold institutional WRDS licences that include Revelio Labs.

1. Check whether your institution subscribes to WRDS:
   [wrds-www.wharton.upenn.edu](https://wrds-www.wharton.upenn.edu)
2. Register for a WRDS account using your institutional email address.
3. Navigate to **Revelio Labs** in the data vendor list and request access.
4. Download the Job Postings and Company Measures tables for the desired date range
   and firm universe.

> **UBC students:** Contact the UBC Library research data team or your faculty
> supervisor to confirm whether UBC's WRDS subscription includes Revelio Labs.

### Option 2 — Direct Academic Licence

Revelio Labs offers project-specific, one-time data delivery at a discounted price for
academic research, as well as institutional licences for universities not on WRDS.

Contact: **research@reveliolabs.com**

Include the following in your inquiry:

- Institutional affiliation and supervisor name
- A brief description of the research project
- The specific datasets required (Job Postings, Company Measures)
- Desired firm universe and date range
- Whether you need a one-time delivery or ongoing access

More information: [reveliolabs.com/products/research](https://www.reveliolabs.com/products/research/)

---

## Data Handling Notes

- **Do not commit data files to this repository.** All parquet files are listed in
  `.gitignore`.
- The Revelio Labs licence agreement prohibits redistribution. Treat all downloaded
  files as confidential.
- Revelio Labs uses a **pro-forma subsidiary mapping** by default: acquired subsidiaries
  are retroactively rolled into the parent company's headcount. Be aware of this when
  interpreting headcount growth around M&A events.
- Company identifiers include CUSIP, GVKEY, ISIN, and Ticker. This project uses
  `ticker` as the primary key; verify ticker continuity for firms that have undergone
  name changes or delistings over the 2009–2024 window.

---

## Sample Data

Revelio Labs provides a free sample of their company reference data on their website:
[reveliolabs.com/products/research](https://www.reveliolabs.com/products/research/).
This sample is useful for testing the pipeline schema but does not include the full
job postings or company measures tables needed to reproduce the results.

---

*For questions about data access, contact your institutional library or reach out to
Revelio Labs directly at research@reveliolabs.com.*
