/**
 * frontend/js/dashboard.js
 * Interactive Dashboard Generator (Section 27) and the Reports/export
 * screen (Section 31).
 */

const DashboardState = {
  activeFilters: {},
  selectedMetric: null,
  lastDashboard: null,
};

const PALETTE = [
  "#2f6f6b", // teal
  "#d69a2d", // amber
  "#3b82f6", // blue
  "#b5432e", // rust
  "#8a6fb0", // purple
  "#34785a", // emerald
  "#e07a5f", // terracotta
  "#457b9d", // steel blue
  "#f4a261", // sandy orange
  "#2a9d8f", // dark cyan
];

function getPlotlyConfig(title) {
  return {
    displayModeBar: "hover",
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d"],
    toImageButtonOptions: {
      format: "png",
      filename: title ? title.toLowerCase().replace(/[^a-z0-9]+/g, "-") : "chart",
      height: 500,
      width: 750,
      scale: 2,
    },
  };
}

function getBaseLayout() {
  return {
    margin: { t: 15, l: 55, r: 25, b: 50 },
    height: 290,
    autosize: true,
    font: { family: "IBM Plex Sans, sans-serif", size: 11, color: "#1a2226" },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    xaxis: {
      gridcolor: "rgba(0,0,0,0.06)",
      zerolinecolor: "rgba(0,0,0,0.12)",
      automargin: true,
    },
    yaxis: {
      gridcolor: "rgba(0,0,0,0.06)",
      zerolinecolor: "rgba(0,0,0,0.12)",
      automargin: true,
    },
    hoverlabel: {
      font: { family: "IBM Plex Sans, sans-serif", size: 12 },
      bgcolor: "#12181c",
      bordercolor: "#12181c",
      namelength: -1,
    },
  };
}

function renderChart(container, spec, isModal = false) {
  const wide = spec.chart_type === "correlation_heatmap" && !isModal;
  const card = document.createElement("div");
  card.className = isModal ? "chart-modal-body" : `chart-card${wide ? " wide" : ""}`;

  const plotId = `plot-${Math.random().toString(36).slice(2)}`;
  const titleText = spec.title || spec.chart_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  if (!isModal) {
    card.innerHTML = `
      <div class="chart-card-header">
        <div>
          <div class="chart-card-title">${escapeHtml(titleText)}</div>
          <div class="chart-card-reason">${escapeHtml(spec.reason || "")}</div>
        </div>
        <div class="chart-card-actions">
          <button class="btn-chart-action" data-action="maximize" title="Maximize chart">⛶</button>
          <button class="btn-chart-action" data-action="download" title="Download chart as PNG">↓</button>
        </div>
      </div>
      <div class="chart-plot" id="${plotId}"></div>
    `;
    container.appendChild(card);

    card.querySelector('[data-action="maximize"]')?.addEventListener("click", () => openChartModal(spec));
    card.querySelector('[data-action="download"]')?.addEventListener("click", () => {
      const plotEl = document.getElementById(plotId);
      if (plotEl && typeof Plotly !== "undefined") {
        Plotly.downloadImage(plotEl, {
          format: "png",
          filename: titleText.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
          height: 600,
          width: 900,
          scale: 2,
        });
      }
    });
  } else {
    card.innerHTML = `<div class="chart-plot modal-plot" id="${plotId}"></div>`;
    container.appendChild(card);
  }

  const layout = getBaseLayout();
  if (isModal) {
    layout.height = 480;
    layout.margin = { t: 20, l: 70, r: 30, b: 70 };
  }
  const config = getPlotlyConfig(titleText);

  try {
    if (typeof Plotly === "undefined") {
      document.getElementById(plotId).innerHTML = '<p class="small muted">Plotly library is loading or unavailable.</p>';
      return;
    }

    const plotEl = document.getElementById(plotId);

    if (spec.chart_type === "line" && spec.data && spec.data.series) {
      Plotly.newPlot(
        plotId,
        [
          {
            x: spec.data.series.map((p) => p.period),
            y: spec.data.series.map((p) => p.value),
            type: "scatter",
            mode: "lines+markers",
            line: { color: "#2f6f6b", width: 2.5, shape: "spline" },
            marker: { color: "#2f6f6b", size: 6 },
            fill: "tozeroy",
            fillcolor: "rgba(47, 111, 107, 0.08)",
            hovertemplate: "<b>%{x}</b><br>Value: <b>%{y:,.2f}</b><extra></extra>",
          },
        ],
        layout,
        config
      );
    } else if ((spec.chart_type === "bar" || spec.chart_type === "horizontal_bar_top_n") && spec.data && spec.data.top) {
      const entries = Object.entries(spec.data.top);
      const horizontal = spec.chart_type === "horizontal_bar_top_n";
      const categoryCol = spec.data.category_column || spec.x || spec.category;

      if (horizontal) {
        const sorted = [...entries].reverse();
        Plotly.newPlot(
          plotId,
          [
            {
              y: sorted.map((e) => e[0]),
              x: sorted.map((e) => e[1]),
              type: "bar",
              orientation: "h",
              marker: {
                color: sorted.map((_, i) => PALETTE[i % PALETTE.length]),
                line: { width: 0 },
              },
              hovertemplate: `<b>%{y}</b><br>Value: <b>%{x:,.2f}</b><br><span style="font-size:10px;color:#d69a2d;">Click bar to filter</span><extra></extra>`,
            },
          ],
          { ...layout, margin: { t: 15, l: 95, r: 25, b: 40 } },
          config
        );
      } else {
        Plotly.newPlot(
          plotId,
          [
            {
              x: entries.map((e) => e[0]),
              y: entries.map((e) => e[1]),
              type: "bar",
              marker: {
                color: entries.map((_, i) => PALETTE[i % PALETTE.length]),
                line: { width: 0 },
              },
              hovertemplate: `<b>%{x}</b><br>Value: <b>%{y:,.2f}</b><br><span style="font-size:10px;color:#d69a2d;">Click bar to filter</span><extra></extra>`,
            },
          ],
          layout,
          config
        );
      }

      // Attach click-to-filter cross-filtering handler
      if (plotEl && categoryCol) {
        plotEl.on("plotly_click", (eventData) => {
          if (!eventData || !eventData.points || !eventData.points.length) return;
          const pt = eventData.points[0];
          const val = horizontal ? pt.y : pt.x;
          if (val) {
            applyFilter(categoryCol, String(val));
          }
        });
      }
    } else if (spec.chart_type === "donut" && spec.data && spec.data.top) {
      const entries = Object.entries(spec.data.top);
      const categoryCol = spec.data.category_column || spec.category || spec.x;

      Plotly.newPlot(
        plotId,
        [
          {
            labels: entries.map((e) => e[0]),
            values: entries.map((e) => e[1]),
            type: "pie",
            hole: 0.55,
            marker: { colors: PALETTE },
            textinfo: "percent",
            hovertemplate: `<b>%{label}</b><br>Value: <b>%{value:,.2f}</b><br>Share: <b>%{percent}</b><br><span style="font-size:10px;color:#d69a2d;">Click slice to filter</span><extra></extra>`,
          },
        ],
        {
          ...layout,
          showlegend: true,
          legend: { orientation: "h", y: -0.15, font: { size: 10 } },
        },
        config
      );

      // Attach click-to-filter cross-filtering handler
      if (plotEl && categoryCol) {
        plotEl.on("plotly_click", (eventData) => {
          if (!eventData || !eventData.points || !eventData.points.length) return;
          const pt = eventData.points[0];
          const val = pt.label;
          if (val) {
            applyFilter(categoryCol, String(val));
          }
        });
      }
    } else if (spec.chart_type === "histogram" && spec.data && spec.data.values) {
      Plotly.newPlot(
        plotId,
        [
          {
            x: spec.data.values,
            type: "histogram",
            marker: { color: "#2f6f6b", line: { color: "#ffffff", width: 1 } },
            hovertemplate: "Range: <b>%{x}</b><br>Count: <b>%{y}</b><extra></extra>",
          },
        ],
        layout,
        config
      );
    } else if (spec.chart_type === "scatter" && spec.data && spec.data.x) {
      Plotly.newPlot(
        plotId,
        [
          {
            x: spec.data.x,
            y: spec.data.y,
            mode: "markers",
            type: "scatter",
            marker: { color: "#b5432e", size: 6, opacity: 0.7, line: { width: 1, color: "#ffffff" } },
            hovertemplate: `${spec.data.x_column || "X"}: <b>%{x:,.2f}</b><br>${spec.data.y_column || "Y"}: <b>%{y:,.2f}</b><extra></extra>`,
          },
        ],
        layout,
        config
      );
    } else if (spec.chart_type === "correlation_heatmap" && spec.data && spec.data.matrix) {
      const columns = Object.keys(spec.data.matrix);
      const z = columns.map((r) => columns.map((c) => spec.data.matrix[r][c]));
      Plotly.newPlot(
        plotId,
        [
          {
            z,
            x: columns,
            y: columns,
            type: "heatmap",
            colorscale: "RdBu",
            zmin: -1,
            zmax: 1,
            hovertemplate: "<b>%{y}</b> × <b>%{x}</b><br>Correlation: <b>%{z:.3f}</b><extra></extra>",
          },
        ],
        { ...layout, height: isModal ? 520 : 380, margin: { t: 15, l: 90, r: 25, b: 90 } },
        config
      );
    } else {
      document.getElementById(plotId).innerHTML = '<p class="small muted">No data available for this chart specification.</p>';
    }

    // Auto-resize observer
    if (window.ResizeObserver && plotEl) {
      const ro = new ResizeObserver(() => {
        Plotly.Plots.resize(plotEl);
      });
      ro.observe(card);
    }
  } catch (e) {
    console.error("Chart render error:", e);
    document.getElementById(plotId).innerHTML = '<p class="small muted">Could not render this chart.</p>';
  }
}

function openChartModal(spec) {
  let modal = document.getElementById("chart-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "chart-modal";
    modal.className = "chart-modal";
    modal.innerHTML = `
      <div class="chart-modal-backdrop" id="chart-modal-backdrop"></div>
      <div class="chart-modal-content">
        <div class="chart-modal-header">
          <div>
            <h3 class="chart-modal-title" id="chart-modal-title"></h3>
            <p class="chart-modal-subtitle small muted" id="chart-modal-subtitle"></p>
          </div>
          <button class="btn-icon" id="btn-close-chart-modal" title="Close">✕</button>
        </div>
        <div id="chart-modal-container"></div>
      </div>
    `;
    document.body.appendChild(modal);

    document.getElementById("btn-close-chart-modal").addEventListener("click", closeChartModal);
    document.getElementById("chart-modal-backdrop").addEventListener("click", closeChartModal);
  }

  const titleText = spec.title || spec.chart_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  document.getElementById("chart-modal-title").textContent = titleText;
  document.getElementById("chart-modal-subtitle").textContent = spec.reason || "";
  const container = document.getElementById("chart-modal-container");
  container.innerHTML = "";

  modal.style.display = "flex";
  renderChart(container, spec, true);
}

function closeChartModal() {
  const modal = document.getElementById("chart-modal");
  if (modal) modal.style.display = "none";
}

function applyFilter(col, val) {
  if (!val) {
    delete DashboardState.activeFilters[col];
  } else {
    DashboardState.activeFilters[col] = val;
    showToast(`Filtering by ${col.replace(/_/g, " ")}: ${val}`, "info");
  }
  loadDashboardScreen();
}

function clearAllFilters() {
  DashboardState.activeFilters = {};
  showToast("All filters cleared", "info");
  loadDashboardScreen();
}

function selectMetric(metric) {
  DashboardState.selectedMetric = metric;
  showToast(`Active metric switched to: ${metric.replace(/_/g, " ")}`, "info");
  loadDashboardScreen();
}

async function loadDashboardScreen() {
  if (!requireDataset()) return;
  const datasetId = AppState.datasetId;
  if (DashboardState.datasetId !== datasetId) {
    const saved = await apiFetch(`/api/projects/${datasetId}`);
    DashboardState.datasetId = datasetId;
    DashboardState.activeFilters = saved.dashboard.filters || {};
    DashboardState.selectedMetric = saved.dashboard.metric || null;
    DashboardState.lastDashboard = null;
  }
  const kpiEl = document.getElementById("dashboard-kpis");
  const chartsEl = document.getElementById("dashboard-charts");
  kpiEl.innerHTML = '<span class="spinner"></span> Loading interactive dashboard…';

  try {
    const params = new URLSearchParams();
    if (DashboardState.selectedMetric) {
      params.set("metric", DashboardState.selectedMetric);
    }
    if (Object.keys(DashboardState.activeFilters).length > 0) {
      params.set("filters", JSON.stringify(DashboardState.activeFilters));
    }

    const queryStr = params.toString() ? `?${params.toString()}` : "";
    const dashboard = await apiFetch(`/api/dashboard/${datasetId}${queryStr}`);
    if (datasetId !== AppState.datasetId) return;
    DashboardState.lastDashboard = dashboard;

    const pbiBtn = document.getElementById("btn-download-powerbi");
    if (pbiBtn) {
      pbiBtn.href = `${API_BASE}/api/dashboard/${AppState.datasetId}/export/powerbi`;
    }

    // Render KPIs
    kpiEl.innerHTML = dashboard.kpis
      .map(
        (kpi) =>
          `<div class="kpi-card">
            <div class="kpi-label">${escapeHtml(kpi.label)}</div>
            <div class="kpi-value">${formatNumber(kpi.value)}</div>
            ${kpi.source_column ? `<div class="kpi-source small muted">${escapeHtml(kpi.source_column.replace(/_/g, " "))}</div>` : ""}
          </div>`
      )
      .join("");

    // Render Toolbar Filters & Metric Selector
    const filtersContainer = document.getElementById("dashboard-filters");
    if (filtersContainer) {
      const totalRows = dashboard.filters.total_rows || 0;
      const filteredRows = dashboard.filters.filtered_rows ?? totalRows;
      const isFiltered = totalRows > 0 && filteredRows < totalRows;

      let toolbarHtml = `
        <div class="filter-controls-group">
          <div class="filter-chip metric-chip">
            <label class="filter-chip-label">Metric</label>
            <select id="dashboard-metric-select">
              ${(dashboard.filters.available_metrics || [])
                .map(
                  (m) =>
                    `<option value="${escapeHtml(m)}" ${
                      m === dashboard.filters.selected_metric ? "selected" : ""
                    }>${escapeHtml(m.replace(/_/g, " "))}</option>`
                )
                .join("")}
            </select>
          </div>
      `;

      toolbarHtml += Object.entries(dashboard.filters.categorical_filters || {})
        .map(
          ([col, values]) => `
        <div class="filter-chip">
          <label class="filter-chip-label">${escapeHtml(col.replace(/_/g, " "))}</label>
          <select data-filter-column="${escapeHtml(col)}">
            <option value="">All (${values.length})</option>
            ${values
              .map(
                (v) =>
                  `<option value="${escapeHtml(v)}" ${
                    DashboardState.activeFilters[col] === String(v) ? "selected" : ""
                  }>${escapeHtml(v)}</option>`
              )
              .join("")}
          </select>
        </div>`
        )
        .join("");

      toolbarHtml += `</div>`;

      // Status indicator and Reset button
      toolbarHtml += `
        <div class="dashboard-toolbar-actions">
          <span class="record-badge ${isFiltered ? "active-filtered" : ""}">
            ${
              isFiltered
                ? `Showing <strong>${filteredRows.toLocaleString()}</strong> of ${totalRows.toLocaleString()} records`
                : `<strong>${totalRows.toLocaleString()}</strong> records`
            }
          </span>
          ${
            isFiltered
              ? `<button class="btn btn-sm btn-accent" id="btn-clear-all-filters">Clear filters</button>`
              : ""
          }
        </div>
      `;

      filtersContainer.innerHTML = toolbarHtml;

      // Event listener for metric select
      const metricSelect = document.getElementById("dashboard-metric-select");
      if (metricSelect) {
        metricSelect.addEventListener("change", (e) => selectMetric(e.target.value));
      }

      // Event listeners for filter selects
      filtersContainer.querySelectorAll("select[data-filter-column]").forEach((select) => {
        select.addEventListener("change", (e) => {
          const col = e.target.getAttribute("data-filter-column");
          applyFilter(col, e.target.value);
        });
      });

      // Clear all filters button
      const clearBtn = document.getElementById("btn-clear-all-filters");
      if (clearBtn) {
        clearBtn.addEventListener("click", clearAllFilters);
      }
    }

    // Render Active Filter Chips Row
    let activePillsContainer = document.getElementById("dashboard-active-pills");
    if (!activePillsContainer) {
      activePillsContainer = document.createElement("div");
      activePillsContainer.id = "dashboard-active-pills";
      activePillsContainer.className = "active-pills-row";
      chartsEl.parentNode.insertBefore(activePillsContainer, chartsEl);
    }

    const activeFilterEntries = Object.entries(DashboardState.activeFilters);
    if (activeFilterEntries.length > 0) {
      activePillsContainer.innerHTML = `
        <div class="active-pills-label">Active filters:</div>
        ${activeFilterEntries
          .map(
            ([col, val]) => `
          <div class="active-pill">
            <span class="active-pill-key">${escapeHtml(col.replace(/_/g, " "))}:</span>
            <span class="active-pill-val">${escapeHtml(typeof val === "object" ? JSON.stringify(val) : val)}</span>
            <button class="active-pill-remove" data-remove-filter="${escapeHtml(col)}" title="Remove filter">✕</button>
          </div>`
          )
          .join("")}
      `;
      activePillsContainer.style.display = "flex";

      activePillsContainer.querySelectorAll("[data-remove-filter]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          const col = e.currentTarget.getAttribute("data-remove-filter");
          applyFilter(col, "");
        });
      });
    } else {
      activePillsContainer.style.display = "none";
      activePillsContainer.innerHTML = "";
    }

    // Render Charts
    chartsEl.innerHTML = "";
    if (dashboard.charts && dashboard.charts.length) {
      dashboard.charts.forEach((spec) => renderChart(chartsEl, spec));
    } else {
      chartsEl.innerHTML = '<div class="card"><p class="small muted">No charts generated for this dataset.</p></div>';
    }
  } catch (err) {
    kpiEl.innerHTML = "";
    chartsEl.innerHTML = "";
    showError(err);
  }
}

async function loadReportsScreen() {
  if (!requireDataset()) return;
  const datasetId = AppState.datasetId;
  document.getElementById("export-csv-link").href = `${API_BASE}/api/dashboard/${AppState.datasetId}/export/csv`;
  document.getElementById("export-xlsx-link").href = `${API_BASE}/api/dashboard/${AppState.datasetId}/export/xlsx`;
  const pbiLink = document.getElementById("export-powerbi-link");
  if (pbiLink) pbiLink.href = `${API_BASE}/api/dashboard/${AppState.datasetId}/export/powerbi`;
  const pbidsLink = document.getElementById("export-pbids-link");
  if (pbidsLink) pbidsLink.href = `${API_BASE}/api/dashboard/${AppState.datasetId}/export/pbids`;

  try {
    const [kpiResult, insightResult] = await Promise.all([
      apiFetch(`/api/analytics/${AppState.datasetId}/kpis`),
      apiFetch(`/api/analytics/${AppState.datasetId}/insights`),
    ]);

    if (datasetId !== AppState.datasetId) return;
    document.getElementById("executive-summary-kpis").innerHTML = kpiResult.kpis
      .map(
        (kpi) =>
          `<div class="kpi-card"><div class="kpi-label">${escapeHtml(kpi.label)}</div><div class="kpi-value">${formatNumber(
            kpi.value
          )}</div></div>`
      )
      .join("");

    document.getElementById("executive-summary-insights").innerHTML = insightResult.insights
      .slice(0, 5)
      .map(
        (i) =>
          `<div class="insight-item"><div class="insight-icon">${insightIcon(i.type)}</div><div><div class="insight-message">${escapeHtml(
            i.message
          )}</div></div></div>`
      )
      .join("");
  } catch (err) {
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  registerScreenHandler("dashboard", loadDashboardScreen);
  registerScreenHandler("reports", loadReportsScreen);
  registerScreenHandler("settings", refreshHealthIndicators);
  document.getElementById("btn-refresh-dashboard")?.addEventListener("click", () => {
    loadDashboardScreen();
    showToast("Dashboard refreshed", "info");
  });
});

// Resolve the current dataset at click time, including before dashboard loading finishes.
document.addEventListener("DOMContentLoaded", () => {
  for (const id of ["btn-download-powerbi", "export-powerbi-link"]) {
    const button = document.getElementById(id);
    if (!button) continue;
    button.title = "Excel data for Power BI import. Native PBIX generation is not supported.";
    button.textContent = "Export for Power BI (.xlsx)";
    button.addEventListener("click", async event => {
      event.preventDefault();
      if (!requireDataset() || button.dataset.pending) return;
      button.dataset.pending = "true";
      try {
        const datasetId = AppState.datasetId;
        const response = await fetch(`${API_BASE}/api/dashboard/${datasetId}/export/powerbi`);
        if (!response.ok) { const error = await response.json(); throw new Error(error.detail || "Export unavailable."); }
        if (!(response.headers.get("content-type") || "").includes("spreadsheetml")) throw new Error("Unexpected export format. Check the API connection.");
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a"); link.href = url; link.download = `${datasetId}_cleaned.xlsx`; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (err) { showError(err); }
      finally { delete button.dataset.pending; }
    });
  }
});
