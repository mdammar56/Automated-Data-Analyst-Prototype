/**
 * frontend/js/database.js
 * PostgreSQL Setup Wizard (Section 11), data loading (Section 21) and the
 * SQL / Data Manipulation Workspace (Section 22).
 */

function getDbForm() {
  return {
    host: document.getElementById("db-host").value.trim() || "localhost",
    port: parseInt(document.getElementById("db-port").value, 10) || 5432,
    user: document.getElementById("db-user").value.trim() || "postgres",
    password: document.getElementById("db-password").value,
    database: document.getElementById("db-name").value.trim(),
  };
}

async function testDbConnection() {
  const statusEl = document.getElementById("db-setup-status");
  statusEl.innerHTML = '<span class="spinner"></span> Testing connection…';
  try {
    const form = getDbForm();
    const result = await apiFetch("/api/database/test", { method: "POST", body: form });
    statusEl.innerHTML = result.success
      ? `<span class="badge badge-ok">reachable</span> ${escapeHtml(result.message)}`
      : `<span class="badge badge-danger">failed</span> ${escapeHtml(result.message)}`;
  } catch (err) {
    statusEl.textContent = "";
    showError(err);
  }
}

async function setupDatabase() {
  const statusEl = document.getElementById("db-setup-status");
  const form = getDbForm();
  if (!form.database) {
    showToast("Enter a database name first.", "error");
    return;
  }
  statusEl.innerHTML = '<span class="spinner"></span> Connecting / creating database…';
  try {
    const result = await apiFetch("/api/database/setup", { method: "POST", body: form });
    statusEl.innerHTML = result.success
      ? `<span class="badge badge-ok">connected</span> ${escapeHtml(result.message)}`
      : `<span class="badge badge-danger">failed</span> ${escapeHtml(result.message)}`;
    if (result.success) {
      AppState.databaseName = result.database_name || form.database;
      showToast("PostgreSQL connected.", "success");
      refreshHealthIndicators();
    }
  } catch (err) {
    statusEl.textContent = "";
    showError(err);
  }
}

async function loadDataToDb() {
  if (!requireDataset()) return;
  const statusEl = document.getElementById("load-db-status");
  statusEl.innerHTML = '<span class="spinner"></span> Loading data into PostgreSQL…';
  try {
    const datasetId = AppState.datasetId;
    const tableName = document.getElementById("load-table-name").value.trim() || undefined;
    const result = await apiFetch("/api/database/load", {
      method: "POST",
      body: { dataset_id: AppState.datasetId, table_name: tableName },
    });
    if (datasetId !== AppState.datasetId) return;
    AppState.importedTable = `"public"."${result.table_name.replace(/"/g, '""')}"`;
    const dbName = result.database_name || AppState.databaseName || "data_analytics";
    statusEl.innerHTML = `
      <div style="margin-top: 8px; line-height: 1.6;">
        <span class="badge badge-ok">✓ Data loaded successfully</span><br>
        <strong>Database:</strong> ${escapeHtml(dbName)}<br>
        <strong>Table:</strong> <code class="inline-code">${escapeHtml(result.table_name)}</code><br>
        <strong>Rows loaded:</strong> ${result.rows_loaded.toLocaleString()}
      </div>`;
    document.getElementById("ai-table-name").value = AppState.importedTable;
    await loadSqlMetadata();
    showToast(`Loaded into table "${result.table_name}".`, "success");
    refreshHealthIndicators();
  } catch (err) {
    statusEl.textContent = err.message;
    showError(err);
  }
}

async function runSqlQuery() {
  const statusEl = document.getElementById("sql-status");
  const query = document.getElementById("sql-input").value.trim();
  if (!query) {
    showToast("Enter a SQL query first.", "error");
    return;
  }
  statusEl.innerHTML = '<span class="spinner"></span> Running query…';

  const runOnce = async (confirm) => {
    const url = `/api/sql/query${confirm ? "?confirm=true" : ""}`;
    return apiFetch(url, { method: "POST", body: { dataset_id: AppState.datasetId, query, limit: Number(document.getElementById("sql-limit").value), timeout_ms: Number(document.getElementById("sql-timeout").value) } });
  };

  try {
    let result;
    try {
      result = await runOnce(false);
    } catch (err) {
      if (err.status === 409) {
        const confirmed = window.confirm(
          "This statement modifies data or schema. Are you sure you want to run it?"
        );
        if (!confirmed) {
          statusEl.textContent = "Cancelled.";
          return;
        }
        result = await runOnce(true);
      } else {
        throw err;
      }
    }

    statusEl.innerHTML = `<span class="badge badge-ok">success</span> ${result.row_count} row(s)${
      result.truncated ? " (truncated)" : ""
    }`;

    const thead = document.querySelector("#sql-results-table thead");
    const tbody = document.querySelector("#sql-results-table tbody");
    thead.innerHTML = `<tr>${result.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
    tbody.innerHTML = result.rows
      .map((r) => `<tr>${r.map((v) => `<td>${escapeHtml(v)}</td>`).join("")}</tr>`)
      .join("");
  } catch (err) {
    statusEl.textContent = err.message;
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  registerScreenHandler("sql", loadSqlMetadata);
  document.getElementById("btn-test-connection").addEventListener("click", testDbConnection);
  document.getElementById("btn-setup-database").addEventListener("click", setupDatabase);
  document.getElementById("btn-load-db").addEventListener("click", loadDataToDb);
  document.getElementById("btn-run-sql").addEventListener("click", runSqlQuery);
});

async function loadSqlMetadata() {
  const el = document.getElementById("sql-schema");
  el.textContent = "Loading database schema…";
  try {
    const data = await apiFetch("/api/database/metadata");
    el.innerHTML = `<p>Database: <strong>${escapeHtml(data.database)}</strong> · Active schema: ${escapeHtml(data.schema)} · Search path: ${escapeHtml(data.search_path)}</p><button class="btn" id="sql-refresh-tables">Refresh tables</button>` +
      (data.tables.length ? `<label>Table <select id="sql-table-selector">${data.tables.map(t => `<option value="${escapeHtml(t.reference)}">${escapeHtml(t.reference)}</option>`).join("")}</select></label><p class="small muted">Use the exact reference below in your SQL. Selecting a table does not modify your query.</p><div id="sql-columns"></div>` : "No accessible tables. Load your dataset into PostgreSQL first.");
    document.getElementById("sql-refresh-tables").addEventListener("click", loadSqlMetadata);
    const selector = document.getElementById("sql-table-selector");
    if (selector) {
      if (data.tables.some(t => t.reference === AppState.importedTable)) selector.value = AppState.importedTable;
      const explore = () => {
        const table = data.tables.find(t => t.reference === selector.value);
        AppState.importedTable = table.reference;
        document.getElementById("ai-table-name").value = table.reference;
        document.getElementById("sql-columns").innerHTML = `<code>${escapeHtml(table.reference)}</code>` + table.columns.map(c => `<div><code>${escapeHtml(c.reference)}</code> — ${escapeHtml(c.type)}</div>`).join("");
      };
      selector.addEventListener("change", explore);
      explore();
    }
  } catch (err) { el.textContent = err.message; }
}
