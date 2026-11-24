# Five-stage application update

## Available workflows

1. **Data foundation:** Home lists saved projects. Dataset Profile includes an
   explainable quality score and editable semantic roles, descriptions, and units.
   Data Cleaning asks for confirmation before removing rows. Undo last change
   restores a saved data/dictionary snapshot; Restore original returns to the
   original profiled copy. Original uploaded files are preserved.
2. **SQL reliability:** SQL Workspace discovers actual PostgreSQL schemas/tables
   and synchronizes its selector with Ask Your Data. Imports save the real table
   mapping. Query history is saved with status, duration, row counts, truncation,
   and bounded numeric result summaries. Earlier-version tables are rejected by
   the AI SQL path until reloaded. SQL uses statement timeouts, bounded streaming
   fetches, and read-only transactions for SELECT queries.
3. **Adaptive analysis:** Dashboard retains existing chart recommendations and
   categorical filters, adds numeric/date ranges, and includes a custom chart
   builder for bar, line, scatter, histogram, box, and pie charts. Users select
   axes, aggregation, and date grouping. Plotly's camera control downloads images.
   Settings persist per project. Empty filters produce empty results rather than
   falling back to full-dataset KPIs.
4. **Project analyst:** Ask Your Data defaults to computed project evidence and
   works without PostgreSQL or an AI key. Evidence includes profile, quality,
   cleaning, KPIs, numeric EDA, correlation, insights, and recorded SQL/segmentation
   summaries. When configured, the provider selects relevant evidence IDs; the
   backend renders factual claims from calculations. Invalid provider selections
   fall back to deterministic summaries. SQL mode separately generates a safe
   query against discovered schema and displays actual results. History records
   versions and marks older findings stale.
5. **Reports and comparison:** Reports generates PDF files with a quality chart,
   KPIs, cleaning outcomes, findings, dictionary, filters and version provenance.
   Generated PDFs remain downloadable from saved history. Compare datasets or
   periods by mapping measures, choosing sum/mean/count, confirming units, and
   supplying independent filters. Zero baselines have no percentage change.
   CSV/Excel exports support full or dashboard-filtered data; Excel includes a
   dictionary sheet. Spreadsheet formula-like text is escaped. Power BI imports
   the Excel `cleaned_data` sheet through Get data → Excel workbook.

## Local storage and restart recovery

Each uploaded dataset is a single-owner project. Project metadata, current frame,
undo snapshots, dashboard selections, queries and analysis history are stored in
`data/cleaned/projects.sqlite3`. Frame serialization uses pandas table JSON,
including type metadata, rather than executable pickle files. SQLite transactions
commit project state and undo pointers together. The database has a schema-version
marker and rejects unsupported versions; a future format change will require a
migration. Reports are stored below `data/cleaned/reports/<dataset_id>`.

Back up the entire `data` directory, including original uploads and SQLite state,
while the app is stopped. Do not apply automatic upload-retention deletion to
files referenced by saved projects. The existing retention setting does not
delete saved projects. Legacy uploads are discovered when Home lists projects.

## Authentication and deployment

Local development binds to `127.0.0.1:8000`. It does not require a password unless
`APP_PASSWORD` is configured. This is a single-owner application: the authenticated
owner can access all projects, not a multi-tenant service with separate users.

Before exposing it publicly, configure server-side environment variables:

```dotenv
APP_ENV=production
APP_USERNAME=analyst
APP_PASSWORD=<a unique password of at least 16 characters>
DATABASE_QUERY_ROLE=analyst_reader
```

Production refuses to start without the password and query role. HTTP Basic
authentication covers the frontend, APIs, downloads and health endpoint. Use HTTPS
at your reverse proxy; never send Basic credentials over public plain HTTP.
Database setup/loading use the configured server connection; analytical SELECTs
switch to the restricted role within a read-only transaction. The production SQL
Workspace blocks write statements even when confirmed. Local development retains
the existing explicitly confirmed manual-write workflow.

Provision the query role using your PostgreSQL administrator, granting only
CONNECT to the intended database, USAGE on required schemas, and SELECT on the
intended tables. Grant that role to the application's login so SET ROLE works.
Do not grant superuser, role/database creation, bypass-RLS, server-file, or program
execution privileges. Read-only transactions and query timeouts supplement these
database grants. The app rejects administrative query roles at execution time.
No credentials are persisted in saved-project records.

## Verification and practical boundaries

Run unit/API regressions with `python -m pytest tests -q`. Set
`RUN_POSTGRES_TESTS=1` to include the live PostgreSQL checks; these use temporary
tables or transactions that roll back their fixtures. JavaScript syntax can be
checked with `node --check frontend/js/projects.js`.

Column meanings remain heuristic and user-reviewable; confidence is shown as
inferred versus user-confirmed, not a calibrated probability. Arbitrary analytical
questions may need a custom chart or SQL calculation when no matching evidence
exists. Provider selection cannot introduce new factual claims. Query summaries
describe returned rows and clearly do not imply a complete unbounded result.
Chart displays cap raw points at 5,000 and groups at 100. Comparisons currently
provide aggregate measure and schema/quality differences; category-by-category
reconciliation and collaborative per-user project sharing are future extensions.

Browser interaction was blocked by the computer-use tool's Google Chrome access
permission during verification. Open http://127.0.0.1:8000 in Chrome to use the app.
