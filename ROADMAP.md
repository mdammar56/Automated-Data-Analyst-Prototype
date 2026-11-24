# Five-stage implementation roadmap

Implement these stages in order. Stages 1 and 2 form the first release;
Stages 3 and 4 build adaptive analysis and evidence-backed AI on that foundation;
Stage 5 completes reporting and comparison.

Status: core workflows implemented across all five stages. See
[IMPLEMENTATION.md](IMPLEMENTATION.md) for the shipped behavior, verification,
and remaining boundaries. The checkboxes below are the original detailed
acceptance targets, not an assertion that every advanced target is complete.
The checkboxes below track implementation and verification,
not merely documentation. Existing capabilities must be extended and tested
before a stage is marked complete.

## Existing foundations

The repository already contains CSV/XLSX ingestion, column detection and
profiling, cleaning previews, PostgreSQL schema generation, dashboard chart
recommendations and filters, segmentation, optional AI querying, and exports.
`file_service.py` can also hydrate datasets from files; this is a starting
point for persistence, not a complete saved-project model. AI SQL currently
has a read-only validation check and a statement timeout. These foundations
should be reused rather than replaced without cause.

## Stage 1 — Data foundation

Goal: varied datasets can be interpreted, cleaned safely, and reopened reliably.

- [ ] Create a shared, versioned dataset profile separating storage types from
  semantic roles: numeric, categorical, datetime, identifier, customer ID,
  monetary amount, and unknown. Use values as well as names; expose uncertain
  inferences and allow users to override them.
- [ ] Add an editable data dictionary with original/display/SQL column names,
  types, inferred roles, descriptions, and inference confidence.
- [ ] Add an explainable quality score with missingness, duplicates, and
  consistency components. Show applicability and limitations of each check.
- [ ] Preserve original uploads and record cleaning operations against explicit
  dataset versions. Preview affected rows and cells, distinguish removed rows
  from changed values, and require confirmation for destructive operations.
- [ ] Add Undo Cleaning and restore-original actions that restore data and
  metadata together, with an audit history that survives restarting the backend.
- [ ] Persist projects, dataset references, type/role overrides, cleaning
  configurations, active versions, dashboard settings, query history, and report
  metadata. Later stages populate their respective records.
- [ ] Add project listing/reopening, atomic persistence, metadata migrations,
  and clear recovery errors for missing or corrupt files.
- [ ] Invalidate cached analysis when data, semantic roles, or cleaning changes.

Primary integration points: `backend/services/file_service.py`,
`profiling_service.py`, `cleaning_service.py`, `backend/utils/column_detector.py`,
profile/upload/cleaning API routes, and their frontend screens.

Completion criteria: exercise CSV and XLSX datasets with unrelated schemas,
numeric identifiers, ambiguous dates, and missing monetary/customer fields.
Verify user overrides affect downstream analysis; cleaning previews match
actual changes; undo restores the prior version; and reopening after a backend
restart restores project state without requiring another upload. Unsupported
analyses explain what data is missing.

## Stage 2 — SQL reliability and safeguards

Depends on Stage 1 project identities and dataset versions.

- [ ] Discover accessible PostgreSQL schemas, actual table names, column names,
  and database types. Persist the dataset-to-schema/table mapping after loading.
- [ ] Add a table selector and schema explorer; refresh after loading, switching
  connections, or changing tables. Use schema-qualified, quoted identifiers.
- [ ] Synchronize SQL Workspace and Ask Your Data with the selected table;
  detect deleted tables and stale dataset-to-table mappings with useful errors.
- [ ] Save per-project query history, selected table, execution status, duration,
  row count, and dataset version; allow reopening and explicitly rerunning SQL.
- [ ] Enforce read-only AI query execution using a restricted database role and
  read-only transactions in addition to SQL validation. Keep administrative
  database setup/loading separate from query execution.
- [ ] Apply configurable statement timeouts and server-side result row limits
  to manual and AI queries; clearly label truncated results.
- [ ] Add authentication and project authorization before public exposure,
  including protection for uploads, downloads, database setup, and AI endpoints.
- [ ] Keep credentials server-side, exclude them from saved projects and logs,
  and document secure configuration and local-versus-public deployment modes.

Primary integration points: `backend/database.py`, `backend/config.py`,
`backend/services/database_service.py`, `schema_service.py`, SQL/database/AI
routes, and `frontend/js/database.js`.

Completion criteria: use opt-in live PostgreSQL tests for non-default schemas,
renamed/missing tables, restricted privileges, attempted writes, timeouts, and
bounded results. Verify history survives restarts and unauthorized users cannot
read or modify another project's resources. Public deployment remains gated
until authentication and authorization checks pass.

## Stage 3 — Adaptive analysis

Depends on Stage 1 profiles and saved settings, and Stage 2 table synchronization
for database-backed analysis.

- [ ] Recommend charts from types, cardinality, semantic roles, and computed
  relationships, with a short explanation for each recommendation.
- [ ] Allow chart-type changes, axis selection, aggregation selection, date
  granularity, and chart image downloads. Prevent invalid combinations and
  accidental sums of identifiers.
- [ ] Extend existing dashboard filters with categorical, numeric-range, and
  date-range controls; apply a single filter context to charts and KPI cards.
- [ ] Save dashboard selections and filters per project and dataset version.
- [ ] Make EDA and segmentation consume the shared profile, allow role
  corrections, and explain prerequisites when an analysis is unavailable.
- [ ] Handle empty filtered results, high-cardinality categories, and large
  datasets with clear sampling/aggregation notices.

Primary integration points: dashboard/visualization/analytics/insight services,
`backend/ml/`, dashboard/analytics routes, and `frontend/js/dashboard.js` and
`analytics.js`.

Completion criteria: unrelated datasets receive valid chart suggestions;
filters produce the same totals across KPI cards, charts, and downloads;
changing axes/types works; saved selections reopen correctly; and datasets
without customer or monetary columns still provide meaningful general EDA.

## Stage 4 — Project-wide AI analyst

Depends on versioned project state, safe SQL, and computed analysis results.

- [ ] Create a shared analytical context containing profile and quality facts,
  cleaning outcomes, bounded SQL results, dashboard metrics and filters, EDA
  findings, and segmentation summaries.
- [ ] Attach provenance to results: project, dataset version, computation/query,
  filters, timestamp, units, and evidence identifiers.
- [ ] Extend Ask Your Data to answer across this context, explain findings, and
  recommend next steps. Support profile/cleaning/EDA questions without requiring
  PostgreSQL when the necessary computed evidence exists locally.
- [ ] Validate numerical claims against computed evidence, distinguish observed
  relationships from causal claims, and state when evidence is insufficient.
- [ ] Show supporting evidence with answers and mark earlier answers/reports
  stale after relevant data or settings change.
- [ ] Generate an executive summary from validated findings; preserve a useful
  deterministic summary when no AI provider is configured.
- [ ] Bound provider context, exclude credentials and raw datasets, treat data
  text as untrusted input, and persist conversations with provenance.

Primary integration points: `backend/services/ai_service.py`, AI routes,
`frontend/js/ai.js`, analysis services, and Stage 1 project storage.

Completion criteria: cross-feature questions cite actual computed results;
unsupported claims are withheld or qualified; stale findings are identified;
prompt-like dataset contents cannot grant query permissions; and missing AI
credentials or provider failures do not break non-AI analytics.

## Stage 5 — Reporting and comparison

Depends on consistent filter context, provenance, and validated summaries.

- [ ] Compare datasets or reporting periods with explicit column mapping,
  compatible types/units, date boundaries, and baseline selection.
- [ ] Report absolute and percentage changes, missing categories, schema
  differences, and quality differences. Handle zero or missing baselines
  explicitly rather than inventing percentage changes.
- [ ] Generate downloadable PDF analytical reports containing dataset/version,
  filters, quality, cleaning changes, KPIs, charts, findings, and limitations.
- [ ] Extend existing CSV/XLSX and Power BI export support with documented
  import steps, data types, consistent date/number formats, and a data dictionary.
  Distinguish an import-compatible export from a native Power BI report.
- [ ] Let users choose full-data versus filtered-data exports and protect
  spreadsheet exports from formula injection while preserving numeric values.
- [ ] Save report/export metadata and comparison configuration per project;
  preserve historical report provenance and identify stale reports.

Primary integration points: dashboard export routes,
`backend/services/powerbi_service.py`, dashboard/report frontend, and new
comparison/report services backed by saved projects.

Completion criteria: comparison fixtures produce known deltas, including zero
baselines and incompatible schemas; PDFs render readable tables and charts;
CSV/XLSX exports round-trip with expected rows, columns, and dates; and the
documented Power BI import workflow uses the actual exported formats.

## Delivery and verification

Deliver each stage as backend behavior, API contracts, usable frontend controls,
documentation, and targeted regression checks. Run the existing suite before
and after implementation, and record live PostgreSQL or browser checks that
could not be run. Do not mark a stage complete based only on endpoint existence.

Release 1: Stages 1–2. Release 2: Stages 3–4. Release 3: Stage 5.
Authentication and authorization are prerequisites for any public release,
regardless of this grouping.
