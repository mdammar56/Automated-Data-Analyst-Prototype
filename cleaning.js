let cleaningPlan = null;
/**
 * frontend/js/cleaning.js
 * Data Cleaning Engine screen (Sections 16-20) and the Data Preview screen.
 */

function getCleaningOptions() {
  return {
    handle_missing: document.getElementById("opt-missing").checked,
    remove_exact_duplicates: document.getElementById("opt-duplicates").checked,
    fix_invalid_values: true,
    flag_outliers: document.getElementById("opt-outliers").checked,
    run_anomaly_detection: document.getElementById("opt-anomalies").checked,
  };
}

async function loadCleaningScreen() {
  if (AppState.datasetId && !AppState.columnProfiles.length) await loadProfileScreen();
  const emptyEl = document.getElementById("cleaning-empty");
  const contentEl = document.getElementById("cleaning-content");
  if (!AppState.datasetId || AppState.columnProfiles.length === 0) {
    emptyEl.style.display = "block";
    contentEl.style.display = "none";
    return;
  }
  emptyEl.style.display = "none";
  contentEl.style.display = "block";
  document.getElementById("cleaning-preview-card").style.display = "none";
  document.getElementById("cleaning-result-card").style.display = "none";
  document.getElementById("audit-log-card").style.display = "none";
}

async function previewCleaning() {
  if (!requireDataset()) return;
  const btn = document.getElementById("btn-preview-cleaning");
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = "Generating plan…";
  document.getElementById("cleaning-status").textContent = "Generating cleaning recommendations…";
  try {
    const options = getCleaningOptions();
    const datasetId = AppState.datasetId;
    const preview = await apiFetch(`/api/cleaning/${AppState.datasetId}/preview`, {
      method: "POST",
      body: options,
    });

    if (datasetId !== AppState.datasetId) return;
    cleaningPlan = {datasetId, options};
    document.getElementById("cleaning-status").textContent = "Cleaning plan ready in Data Quality.";
    goToScreen("quality");
    document.getElementById("cleaning-preview-card").style.display = "block";
    document.getElementById("quality-summary-cards").innerHTML = `
      <div class="kpi-card"><div class="kpi-label">Rows (before)</div><div class="kpi-value">${preview.before_summary.rows}</div></div>
      <div class="kpi-card"><div class="kpi-label">Missing cells (before)</div><div class="kpi-value">${preview.before_summary.missing_cells}</div></div>
      <div class="kpi-card"><div class="kpi-label">Duplicate rows</div><div class="kpi-value">${preview.before_summary.duplicate_rows}</div></div>
      <div class="kpi-card"><div class="kpi-label">Estimated rows (after)</div><div class="kpi-value">${preview.estimated_after_summary.rows}</div></div>
    `;

    const planEl = document.getElementById("cleaning-plan");
    planEl.innerHTML = preview.plan
      .map((step) => {
        let detailHtml = "";
        if (step.step === "missing_values" && Array.isArray(step.detail)) {
          detailHtml = step.detail.length
            ? `<table class="data-table"><thead><tr><th>Column</th><th>Missing</th><th>Strategy</th><th>Reason</th></tr></thead><tbody>${step.detail
                .map(
                  (d) =>
                    `<tr><td class="mono">${escapeHtml(d.column)}</td><td>${d.missing_count} (${d.missing_percent}%)</td><td><span class="badge badge-neutral">${escapeHtml(d.strategy)}</span></td><td class="small muted">${escapeHtml(d.reason)}</td></tr>`
                )
                .join("")}</tbody></table>`
            : '<p class="small muted">No missing values detected.</p>';
        } else {
          detailHtml = `<pre class="small mono" style="white-space:pre-wrap;">${escapeHtml(JSON.stringify(step.detail, null, 2))}</pre>`;
        }
        return `<div class="plan-step"><div class="plan-step-title">${escapeHtml(step.step.replace(/_/g, " "))}</div>${detailHtml}</div>`;
      })
      .join("");
  } catch (err) {
    document.getElementById("cleaning-status").textContent = `Could not generate cleaning plan: ${err.message}`;
    showError(err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Preview cleaning plan";
  }
}

async function applyCleaning() {
  if (!requireDataset()) return;
  if (!cleaningPlan || cleaningPlan.datasetId !== AppState.datasetId) {
    showToast("Preview a cleaning plan for this dataset first.", "error"); return;
  }
  const btn = document.getElementById("btn-apply-cleaning");
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = "Applying…";
  const datasetId = AppState.datasetId;
  try {
    try {
      await apiFetch(`/api/cleaning/${datasetId}/apply`, {method: "POST", body: cleaningPlan.options});
    } catch (err) {
      if (err.status !== 409) throw err;
      if (!window.confirm(err.message + " Continue?")) return;
      await apiFetch(`/api/cleaning/${datasetId}/apply`, {method: "POST", body: {...cleaningPlan.options, confirm_destructive: true}});
    }
    if (datasetId !== AppState.datasetId) return;
    showToast("Cleaning applied.", "success");
    goToScreen("preview");
  } catch (err) { showError(err); }
  finally { btn.disabled = false; btn.textContent = "Apply cleaning"; }
}

async function loadPreviewScreen() {
  if (!requireDataset()) return;
  try {
    const datasetId = AppState.datasetId;
    const preview = await apiFetch(`/api/cleaning/${datasetId}/data-preview`);
    if (datasetId !== AppState.datasetId) return;
    const header = preview.cleaned.columns;
    const rows = preview.cleaned.rows;
    const result = preview.cleaning;
    document.getElementById("cleaning-result-card").style.display = result ? "block" : "none";
    document.getElementById("audit-log-card").style.display = result ? "block" : "none";
    if (result) {
      document.querySelector("#before-after-table tbody").innerHTML = ["rows", "columns", "missing_cells", "duplicate_rows"].map(m => `<tr><td>${m.replace(/_/g, " ")}</td><td>${result.before[m]}</td><td>${result.after[m]}</td></tr>`).join("");
      document.getElementById("audit-log-list").innerHTML = result.audit_log.map(e => `<div class="audit-entry"><strong>${escapeHtml(e.action)}</strong> ${escapeHtml(JSON.stringify(e.detail))}</div>`).join("");
    }
    document.querySelector("#original-preview-table thead").innerHTML = `<tr>${preview.original.columns.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
    document.querySelector("#original-preview-table tbody").innerHTML = preview.original.rows.map(r => `<tr>${r.map(v => `<td>${escapeHtml(v)}</td>`).join("")}</tr>`).join("");
    const thead = document.querySelector("#preview-table thead");
    const tbody = document.querySelector("#preview-table tbody");
    thead.innerHTML = `<tr>${header.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>`;
    tbody.innerHTML = rows
      .map((r) => `<tr>${r.map((c) => `<td>${escapeHtml(c)}</td>`).join("")}</tr>`)
      .join("");
  } catch (err) {
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  registerScreenHandler("cleaning", loadCleaningScreen);
  registerScreenHandler("preview", loadPreviewScreen);
  registerScreenHandler("quality", () => {
    const ready = cleaningPlan && cleaningPlan.datasetId === AppState.datasetId;
    document.getElementById("cleaning-preview-card").style.display = ready ? "block" : "none";
    document.getElementById("quality-empty").style.display = ready ? "none" : "block";
  });
  document.getElementById("btn-preview-cleaning").addEventListener("click", previewCleaning);
  document.getElementById("btn-apply-cleaning").addEventListener("click", applyCleaning);
});
