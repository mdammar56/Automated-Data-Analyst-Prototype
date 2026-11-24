# Automated Data Analyst

A local, dataset-adaptive analytics application. Upload any sales, retail or
customer-shopping CSV/XLSX file and the app automatically profiles it,
cleans it, loads it into PostgreSQL, and generates KPIs, insights, an
interactive dashboard, and optional AI-assisted natural-language queries.
Nothing is hard-coded to one dataset's schema — every screen adapts to the
columns it actually finds.

## 1. What's inside

```
automated-data-analyst/
├── backend/                 FastAPI application
│   ├── api/                 REST route handlers (one file per feature area)
│   ├── services/            Business logic / orchestration
│   ├── cleaning/            Missing values, duplicates, outliers, anomalies
│   ├── ml/                  Isolation Forest, LOF, RFM, K-Means/DBSCAN
│   ├── utils/                Validators, column-type detection, audit log
│   ├── config.py            Environment configuration (.env loader)
│   ├── database.py          PostgreSQL connection/session management
│   ├── schemas.py           Pydantic request/response models
│   └── main.py              FastAPI app entry point
├── frontend/                 Static HTML/CSS/JS single-page app (no build step)
│   ├── index.html
│   ├── css/
│   └── js/
├── sample_datasets/          Generated sample CSV/XLSX files + generator script
├── tests/                     Pytest suite, including opt-in PostgreSQL regressions
├── data/                      Runtime uploads/cleaned/exports (gitignored)
├── reports/                   Runtime logs (gitignored)
├── requirements.txt
├── .env.example               Copy to .env and fill in your local values
├── run.bat                    One-click Windows launcher
└── README.md                  This file
```

## 2. Requirements

- **Python 3.10+**
- **PostgreSQL 13+** running locally (or reachable over the network) —
  only required once you use the PostgreSQL / SQL Workspace / Ask Your Data
  screens. Upload, profiling, cleaning, EDA, insights, dashboard and
  segmentation all work without a database.
- A modern browser (Chrome, Edge, Firefox).
- (Optional) A Groq API key, only if you want the "Ask Your Data"
  natural-language layer.

## 3. Quick start (Windows)

1. Double-click **`run.bat`**. On first run it will:
   - create a local virtual environment (`.venv`)
   - install everything in `requirements.txt`
   - copy `.env.example` to `.env` if you don't already have one
   - start the backend at `http://localhost:8000`
   - wait for the `/health` endpoint to verify the server is ready
   - open `http://localhost:8000` in your default browser
2. Open the **Settings** screen in the app to confirm the backend is
   reachable and to see whether PostgreSQL/AI are configured yet.
3. Go to **Home / Upload** and upload a file, or use one of the samples in
   `sample_datasets/`.

## 4. Quick start (macOS/Linux, or manual setup)

```bash
cd automated-data-analyst
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit .env with your PostgreSQL password
uvicorn backend.main:app --reload --port 8000
```

Then open `http://localhost:8000` in your browser (FastAPI automatically
serves the single-page frontend and static assets directly).

## 5. Configuring PostgreSQL

You have two options:

1. **In-app setup wizard** (recommended): go to the **PostgreSQL** screen,
   enter your host/port/username/password and a database name, then click
   **Create / Connect**. The backend will test the connection, create the
   database if it doesn't exist, and remember the configuration for the
   rest of the session.
2. **Manually in `.env`**: fill in `DATABASE_HOST`, `DATABASE_PORT`,
   `DATABASE_USER`, `DATABASE_PASSWORD`, and `DATABASE_NAME` before starting
   the backend.

Your password is only ever read server-side from `.env` or the setup-wizard
request body — it is never written to disk in plain view of the frontend,
logged, or sent anywhere except directly to PostgreSQL.

## 6. Enabling the optional AI layer (Groq)

The app is fully functional without this. To enable natural-language
querying on the **Ask Your Data** screen:

1. Get a Groq API key from [Groq Console](https://console.groq.com/keys).
2. Add it to `.env`:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   GROQ_MODEL=openai/gpt-oss-120b
   ```
3. Restart the backend.

The AI layer only ever receives your question plus the target table's
column names/types — never raw row data or credentials — and every
AI-generated SQL statement is checked to be a single read-only `SELECT`
before it is allowed to run.

## 7. Application walkthrough

| Screen | What it does |
|---|---|
| Home / Upload | Validates and uploads a `.csv`/`.xlsx` file |
| Dataset Profile | Standardizes column names, detects types/roles, reports missing values, duplicates, and correlations |
| Data Cleaning | Detect → Explain → Recommend → Preview → Apply, with a full audit log |
| Data Preview | Row-level view of the cleaned dataset |
| PostgreSQL | Setup wizard + load the cleaned dataset into a table |
| SQL Workspace | Run read-only queries freely; destructive statements require confirmation |
| EDA | Distributions, categorical frequencies, correlation heatmap |
| Insights | Automatically detected trends, top performers, concentration, anomalies, correlations |
| Dashboard | KPI cards + auto-recommended charts generated from your schema |
| Customer Segmentation | RFM scoring and K-Means clustering, only offered when the data supports it |
| Ask Your Data | Optional Groq natural-language querying |
| Reports | CSV/XLSX export + an executive summary of KPIs and insights |
| Settings | Connection/AI status and security reminders |

## 8. Running the test suite

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

All tests should pass. They cover upload validation, column
standardization, missing-value/duplicate/outlier/anomaly handling, safe SQL
identifier generation, KPI generation, insight detection, segmentation, and
chart recommendation/dashboard assembly — without requiring a live
PostgreSQL server.

## 9. Sample datasets

Regenerate the bundled sample datasets at any time with:

```bash
python sample_datasets/generate_samples.py
```

This produces three datasets with deliberately different column names,
orderings, and data-quality issues (missing values, duplicates, extreme
values, inconsistent categorical casing) so you can exercise the full,
dataset-adaptive pipeline:

- `sales_sample.csv` — 2,020 rows × 30 columns
- `customer_shopping_sample.csv` — 1,512 rows × 27 columns
- `ecommerce_sample.xlsx` — 3,000 rows × 30 columns

## 10. Security notes

- `.env` is listed in `.gitignore` — never commit it.
- Table/column names are sanitized into safe SQL identifiers before any
  query is built; `CREATE TABLE`/`CREATE DATABASE` statements never
  interpolate raw user input directly.
- The SQL Workspace blocks stacked statements and requires explicit
  `confirm=true` for anything that isn't a plain `SELECT`/`WITH` query.
- Outliers and anomalies are always flagged, never silently deleted —
  a very large but genuine transaction should never disappear from your data.

## 11. Implementation roadmap

The five-stage application update is available. See
[IMPLEMENTATION.md](IMPLEMENTATION.md) for the implemented workflows, persistence,
authentication configuration, verification, and remaining boundaries.

The staged design is tracked in [ROADMAP.md](ROADMAP.md), in this order:

1. **Data foundation** — shared dataset profiles, editable data dictionary,
   explainable quality scores, reversible cleaning, and persistent projects.
2. **SQL reliability and safeguards** — actual schema discovery, table selection,
   query history, database-enforced read-only AI queries, limits, and authentication.
3. **Adaptive analysis** — configurable chart recommendations, consistent filters,
   saved dashboards, and dataset-aware EDA and segmentation.
4. **Project-wide AI analyst** — computed evidence across features, validated
   answers, provenance, and executive summaries.
5. **Reporting and comparison** — dataset/period comparisons, PDF reports, and
   improved CSV, Excel, and Power BI-compatible exports.

The roadmap retains detailed acceptance targets; IMPLEMENTATION.md records the
current implementation and distinguishes supported workflows from future extensions.

## 12. Known limitations (v1)

- Single-owner design: projects and undo history now persist in SQLite and can
  be reopened after restarting. Multi-user project isolation is not implemented.
- Public deployment requires the authentication and database-role configuration
  described in IMPLEMENTATION.md; the default launcher binds only to localhost.
- RFM/K-Means segmentation only appears when the dataset actually contains
  suitable customer/date/amount columns — this is by design, not a bug.
- The frontend is intentionally framework-free (no Node/build step) for
  easy local use; a future version could add a proper multi-user backend.
