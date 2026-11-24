/**
 * frontend/js/profile.js
 * Automatic Dataset Profiling screen (Section 13).
 */

async function loadProfileScreen() {
  const emptyEl = document.getElementById("profile-empty");
  const contentEl = document.getElementById("profile-content");

  if (!AppState.datasetId) {
    emptyEl.style.display = "block";
    contentEl.style.display = "none";
    return;
  }

  emptyEl.innerHTML = '<span class="spinner"></span> Profiling datasetâ€¦';
  emptyEl.style.display = "block";
  contentEl.style.display = "none";

  try {
    const datasetId = AppState.datasetId;
    const profile = await apiFetch(`/api/profile/${datasetId}`);
    if (datasetId !== AppState.datasetId) return;

    AppState.columnProfiles = profile.column_profiles;
    AppState.columnRoles = Object.fromEntries(
      profile.column_profiles.map((c) => [c.standardized_name, c.detected_role])
    );
    AppState.columnDtypes = Object.fromEntries(
      profile.column_profiles.map((c) => [c.standardized_name, c.detected_type])
    );
    AppState.numericColumns = profile.column_profiles
      .filter((c) => ["numeric", "currency_amount", "percentage_rate"].includes(c.detected_role))
      .map((c) => c.standardized_name);
    AppState.categoricalColumns = profile.column_profiles
      .filter((c) => c.detected_role === "categorical")
      .map((c) => c.standardized_name);

    emptyEl.style.display = "none";
    contentEl.style.display = "block";

    document.getElementById("profile-summary-cards").innerHTML = `
      <div class="kpi-card"><div class="kpi-label">Rows</div><div class="kpi-value">${profile.rows.toLocaleString()}</div></div>
      <div class="kpi-card"><div class="kpi-label">Columns</div><div class="kpi-value">${profile.columns}</div></div>
      <div class="kpi-card"><div class="kpi-label">Duplicate rows</div><div class="kpi-value">${profile.duplicate_rows.toLocaleString()}</div></div>
      <div class="kpi-card"><div class="kpi-label">Missing cells</div><div class="kpi-value">${profile.missing_percent}%</div></div>
    `;

    const tbody = document.querySelector("#profile-columns-table tbody");
    tbody.innerHTML = profile.column_profiles
      .map(
        (col) => `
      <tr>
        <td>${escapeHtml(col.original_name)}</td>
        <td class="mono">${escapeHtml(col.standardized_name)}</td>
        <td><span class="badge badge-neutral">${escapeHtml(col.detected_type)}</span></td>
        <td><span class="badge badge-ok">${escapeHtml(col.detected_role)}</span></td>
        <td>${col.missing_percent}%</td>
        <td>${col.unique_count}</td>
        <td class="small muted">${col.sample_values.map(escapeHtml).join(", ")}</td>
      </tr>`
      )
      .join("");
  } catch (err) {
    emptyEl.innerHTML = `<strong>Could not profile dataset</strong>${escapeHtml(err.message)}`;
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  registerScreenHandler("profile", loadProfileScreen);
});
