/* Persistent projects and dataset-adaptive controls. All user text is escaped. */
const ProjectUI = { current: null };
const el = id => document.getElementById(id);
const projectPath = suffix => `/api/projects/${AppState.datasetId}${suffix || ""}`;
const option = (value, label = value) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;

function projectCard(screen, id, title, body) {
  const card = document.createElement("div");
  card.id = id; card.className = "card project-card";
  card.innerHTML = `<h3>${title}</h3>${body}`;
  const section = el(`screen-${screen}`);
  section.insertBefore(card, section.querySelector(".workflow-navigation"));
}
function onClick(id, handler) {
  el(id).addEventListener("click", async () => {
    const button = el(id); button.disabled = true;
    try { await handler(); } catch (err) { showError(err); }
    finally { button.disabled = false; }
  });
}
function enhanceScreen(screen, handler) {
  const existing = SCREEN_ON_ENTER[screen];
  registerScreenHandler(screen, async () => { if (existing) await existing(); await handler(); });
}
async function projectDetail() {
  if (!AppState.datasetId) return null;
  const id = AppState.datasetId;
  const data = await apiFetch(`/api/projects/${id}`);
  if (id !== AppState.datasetId) return null;
  ProjectUI.current = data;
  return data;
}
async function refreshProjects() {
  const projects = await apiFetch("/api/projects");
  el("saved-projects").innerHTML = projects.map(p => option(p.dataset_id, `${p.name} · v${p.version}`)).join("");
  if (projects.some(p => p.dataset_id === AppState.datasetId)) el("saved-projects").value = AppState.datasetId;
  el("saved-count").textContent = `${projects.length} saved projects. Uploads and changes stay on this computer.`;
}
async function openProject() {
  const id = el("saved-projects").value;
  if (!id) return;
  const doc = await apiFetch(`/api/projects/${id}`);
  setDataset(id, doc.name);
  AppState.importedTable = doc.table?.reference || null;
  el("ai-table-name").value = AppState.importedTable || "";
  DashboardState.datasetId = null;
  goToScreen("profile");
}
async function renderDictionary() {
  const doc = await projectDetail();
  if (!doc) return;
  el("quality-score").textContent = `Quality ${doc.quality.score ?? "not scored"}/100 · version ${doc.version} · ${doc.quality.rows} rows`;
  el("quality-explanation").textContent = `${JSON.stringify(doc.quality.components)}. ${doc.quality.explanation}`;
  el("dictionary-body").innerHTML = doc.dictionary.map(d => `<tr>
    <td>${escapeHtml(d.column)}<br><small>${escapeHtml(d.storage_type)} · ${escapeHtml(d.inference)}</small></td>
    <td><select aria-label="Role for ${escapeHtml(d.column)}" data-role>${doc.roles.map(r => `<option ${r === d.role ? "selected" : ""}>${escapeHtml(r)}</option>`).join("")}</select></td>
    <td><input aria-label="Unit for ${escapeHtml(d.column)}" data-unit value="${escapeHtml(d.unit)}" placeholder="e.g. INR, kg" maxlength="50"></td>
    <td><input aria-label="Description for ${escapeHtml(d.column)}" data-description value="${escapeHtml(d.description)}" maxlength="1000"></td>
    <td><button class="btn" data-save-column="${escapeHtml(d.column)}">Save</button></td></tr>`).join("");
  el("dictionary-body").querySelectorAll("[data-save-column]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const row = button.closest("tr");
      await apiFetch(projectPath("/dictionary"), {method: "PUT", body: {column: button.dataset.saveColumn, role: row.querySelector("[data-role]").value, unit: row.querySelector("[data-unit]").value, description: row.querySelector("[data-description]").value}});
      AppState.columnProfiles = []; cleaningPlan = null;
      await loadProfileScreen(); await renderDictionary(); showToast("Column meaning saved. Earlier findings are now marked stale.", "success");
    } catch (err) { showError(err); } finally { button.disabled = false; }
  }));
}
async function restoreProject(action) {
  if (!requireDataset()) return;
  if (action === "restore-original" && !confirm("Restore the original profiled data? This can be undone.")) return;
  await apiFetch(projectPath(`/${action}`), {method: "POST"});
  cleaningPlan = null; AppState.columnProfiles = [];
  await loadProfileScreen(); goToScreen("preview"); showToast("Dataset restored. Earlier results are marked stale.", "success");
}
async function refreshHistory() {
  if (!AppState.datasetId) return;
  const history = await apiFetch(projectPath("/history"));
  el("query-history").innerHTML = history.filter(h => h.kind === "sql").map(h => `<div><button class="btn" data-query-id="${h.id}">Open query</button> ${escapeHtml(h.status)} · ${h.duration_ms} ms · ${h.row_count ?? 0} rows ${h.stale ? "· older dataset version" : ""}<pre>${escapeHtml(h.query)}</pre></div>`).join("") || "No saved queries yet.";
  el("query-history").querySelectorAll("[data-query-id]").forEach(button => button.onclick = () => { el("sql-input").value = history.find(h => h.id === Number(button.dataset.queryId)).query; });
  el("project-history").innerHTML = history.slice(0, 30).map(h => `<details><summary>${escapeHtml(h.kind)} · v${h.version} · ${escapeHtml(h.at)} ${h.stale ? "· STALE" : ""}</summary>${h.kind === "report" && h.filename ? `<a class="btn" href="${API_BASE}${projectPath(`/reports/${encodeURIComponent(h.filename)}`)}">Download saved PDF</a>` : ""}<pre>${escapeHtml(JSON.stringify(h, null, 2))}</pre></details>`).join("") || "No reports or analysis saved yet.";
}
async function populateChartBuilder() {
  const doc = await projectDetail(); if (!doc) return;
  const columns = doc.dictionary.map(d => option(d.column)).join("");
  el("chart-x").innerHTML = columns; el("chart-y").innerHTML = option("", "Count only") + columns;
  el("range-column").innerHTML = columns;
  const saved = doc.dashboard.chart || {};
  for (const [key, id] of Object.entries({x:"chart-x", y:"chart-y", type:"chart-type", aggregation:"chart-aggregation", granularity:"chart-granularity"})) {
    if (saved[key] != null) el(id).value = saved[key];
  }
  if (!saved.x) {
    el("chart-x").value = doc.dictionary.find(d => d.role === "categorical" || d.role === "date_time")?.column || doc.dictionary[0]?.column;
    el("chart-y").value = doc.dictionary.find(d => ["numeric", "currency_amount", "percentage_rate"].includes(d.role))?.column || "";
    if (!el("chart-y").value) el("chart-aggregation").value = "count";
  }
  el("chart-guidance").textContent = "Bar: compare categories. Line: date trends. Scatter: two measures. Histogram/box: a measure's distribution. Identifier sums are blocked.";
  if (saved.x) await buildChart();
}
async function buildChart() {
  if (!requireDataset()) return;
  const spec = {x: el("chart-x").value, y: el("chart-y").value, type: el("chart-type").value, aggregation: el("chart-aggregation").value, granularity: el("chart-granularity").value, filters: DashboardState.activeFilters};
  const result = await apiFetch(projectPath("/chart"), {method:"POST", body:spec});
  await Plotly.newPlot("custom-chart", result.data, result.layout, {responsive:true, displaylogo:false, toImageButtonOptions:{format:"png",filename:"analysis-chart"}});
  el("chart-note").textContent = `${result.rows} filtered rows · v${result.version}. ${result.limited ? "Display limited. " : ""}${result.note}`;
  await apiFetch(projectPath("/dashboard"), {method:"PUT", body:{filters: DashboardState.activeFilters, metric:DashboardState.selectedMetric, chart:spec}});
}
async function prepareReports() {
  if (!AppState.datasetId) return;
  const doc = await projectDetail(); if (!doc) return;
  const projects = await apiFetch("/api/projects");
  el("compare-project").innerHTML = projects.map(p => option(p.dataset_id,p.name)).join("");
  el("compare-column").innerHTML = doc.dictionary.map(d => option(d.column)).join("");
  await populateOtherColumns(); await refreshHistory();
  el("pdf-report").href = `${API_BASE}${projectPath("/report.pdf")}?filtered=true`;
  for (const format of ["csv", "xlsx"]) el(`filtered-${format}`).href = `${API_BASE}/api/dashboard/${AppState.datasetId}/export/${format}?filtered=true`;
}
async function populateOtherColumns() {
  if (!el("compare-project").value) return;
  const doc = await apiFetch(`/api/projects/${el("compare-project").value}`);
  el("compare-other-column").innerHTML = doc.dictionary.map(d => option(d.column)).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  projectCard("upload", "project-picker", "Continue a saved project", `<p id="saved-count"></p><label>Project <select id="saved-projects"></select></label><button class="btn btn-primary" id="open-project">Open project</button><button class="btn" id="refresh-projects">Refresh</button>`);
  projectCard("profile", "dictionary-card", "Quality and data dictionary", `<h4 id="quality-score"></h4><p id="quality-explanation"></p><p>Confirm inferred meanings before analysis. Customer ID is separate from numeric measures. Set units for reliable comparisons.</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Column</th><th>Meaning</th><th>Unit</th><th>Description</th><th>Action</th></tr></thead><tbody id="dictionary-body"></tbody></table></div>`);
  projectCard("cleaning", "undo-card", "Reversible changes", `<p>Your original upload is preserved. Undo restores the previous data and dictionary version.</p><button class="btn" id="undo-cleaning">Undo last change</button><button class="btn" id="restore-original">Restore original data</button>`);
  projectCard("sql", "history-card", "Saved query history", `<button class="btn" id="refresh-history">Refresh history</button><div id="query-history"></div>`);
  projectCard("dashboard", "builder-card", "Explore with your own chart", `<p id="chart-guidance"></p><div class="project-controls">
    <label>Chart <select id="chart-type">${["bar","line","scatter","histogram","box","pie"].map(v=>option(v)).join("")}</select></label>
    <label>X axis <select id="chart-x"></select></label><label>Y measure <select id="chart-y"></select></label>
    <label>Aggregation <select id="chart-aggregation">${["sum","mean","count","min","max"].map(v=>option(v)).join("")}</select></label>
    <label>Date grouping <select id="chart-granularity">${["month","day","year"].map(v=>option(v)).join("")}</select></label><button class="btn btn-primary" id="build-chart">Build and save chart</button></div>
    <h4>Range filter</h4><div class="project-controls"><label>Column <select id="range-column"></select></label><label>Type <select id="range-kind"><option value="numeric">Numeric</option><option value="date">Date (ISO format)</option></select></label><label>From <input id="range-min" placeholder="Number or YYYY-MM-DD"></label><label>To <input id="range-max" placeholder="Number or YYYY-MM-DD"></label><button class="btn" id="apply-range">Apply range</button><button class="btn" id="clear-ranges">Clear all filters</button></div><p id="chart-note"></p><div id="custom-chart" style="min-height:320px"></div>`);
  projectCard("ai", "ai-context-card", "Analysis scope", `<label>Answer using <select id="ai-scope"><option value="project">Computed project evidence (works without PostgreSQL)</option><option value="sql">AI-generated read-only SQL (requires provider and PostgreSQL)</option></select></label><p>Project answers cite computed evidence. A provider can select relevant findings; displayed factual claims come from calculations. No evidence means no supported conclusion.</p>`);
  projectCard("reports", "report-tools", "Reports and comparisons", `<div class="project-controls"><a class="btn btn-primary" id="pdf-report">Download PDF report</a><a class="btn" id="filtered-csv">Filtered CSV</a><a class="btn" id="filtered-xlsx">Filtered Excel</a><button class="btn" id="executive-summary">Generate executive summary</button></div><p>These downloads use saved dashboard filters. Existing export buttons download the full dataset. For Power BI, import the Excel cleaned_data sheet; the data_dictionary sheet documents columns.</p><pre id="summary-result"></pre><h4>Compare datasets or periods</h4><div class="project-controls"><label>Baseline column <select id="compare-column"></select></label><label>Compare with <select id="compare-project"></select></label><label>Current column <select id="compare-other-column"></select></label><label>Aggregation <select id="compare-aggregation"><option>sum</option><option>mean</option><option>count</option></select></label></div><p>Use the same project with different filters to compare periods. Filter JSON accepts column values or ranges, e.g. {"date":{"kind":"date","min":"2025-01-01","max":"2025-12-31"}}.</p><div class="project-controls"><label>Baseline filters <textarea id="compare-filters">{}</textarea></label><label>Current filters <textarea id="compare-other-filters">{}</textarea></label><label><input type="checkbox" id="compare-units"> I confirm both measures use the same units</label><button class="btn" id="compare-run">Compare</button></div><pre id="compare-result"></pre>`);
  projectCard("reports", "project-events", "Saved analysis history", `<div id="project-history"></div>`);
  onClick("open-project", openProject); onClick("refresh-projects", refreshProjects);
  onClick("undo-cleaning", ()=>restoreProject("undo")); onClick("restore-original", ()=>restoreProject("restore-original"));
  onClick("refresh-history", refreshHistory); onClick("build-chart", buildChart);
  onClick("apply-range", async()=> {
    const filters = {...DashboardState.activeFilters, [el("range-column").value]: {kind:el("range-kind").value,min:el("range-min").value,max:el("range-max").value}};
    await apiFetch(projectPath("/dashboard"), {method:"PUT",body:{filters,metric:DashboardState.selectedMetric,chart:ProjectUI.current?.dashboard.chart || {}}});
    DashboardState.activeFilters = filters; await loadDashboardScreen(); await buildChart();
  });
  onClick("clear-ranges", async()=> { DashboardState.activeFilters={}; await loadDashboardScreen(); await buildChart(); });
  onClick("executive-summary", async()=> { const result = await apiFetch(projectPath("/ask"), {method:"POST",body:{question:"Executive summary and recommended next steps"}}); el("summary-result").textContent=result.answer; await refreshHistory(); });
  onClick("compare-run", async()=> { const result=await apiFetch(projectPath("/compare"),{method:"POST",body:{other_id:el("compare-project").value,column:el("compare-column").value,other_column:el("compare-other-column").value,aggregation:el("compare-aggregation").value,confirm_units:el("compare-units").checked,filters:JSON.parse(el("compare-filters").value),other_filters:JSON.parse(el("compare-other-filters").value)}}); el("compare-result").textContent=JSON.stringify(result,null,2); });
  el("compare-project").addEventListener("change",()=>populateOtherColumns().catch(showError));
  enhanceScreen("upload",refreshProjects); enhanceScreen("profile",renderDictionary); enhanceScreen("sql",refreshHistory); enhanceScreen("dashboard",populateChartBuilder); enhanceScreen("reports",prepareReports);
  refreshProjects().catch(showError);
});
