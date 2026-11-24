/**
 * frontend/js/analytics.js
 * EDA (Section 23), Insights (Section 25) and Customer Segmentation
 * (Section 28) screens.
 */

let currentEdaData = null;
let activeEdaColumn = null;

const EDA_PALETTE = [
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

async function loadEdaScreen() {
  if (!requireDataset()) return;
  try {
    const datasetId = AppState.datasetId;
    const eda = await apiFetch(`/api/analytics/${datasetId}/eda`);
    if (datasetId !== AppState.datasetId) return;
    currentEdaData = eda;

    // 1. Numeric distributions
    const distTbody = document.querySelector("#eda-distributions-table tbody");
    const distThead = document.querySelector("#eda-distributions-table thead");
    const distWrapper = document.getElementById("eda-distribution-plot-wrapper");

    const numEntries = Object.entries(eda.distributions || {});
    if (numEntries.length === 0) {
      distThead.innerHTML = "<tr><th>Status</th></tr>";
      distTbody.innerHTML = '<tr><td class="small muted">No numeric columns found in this dataset.</td></tr>';
      if (distWrapper) distWrapper.style.display = "none";
    } else {
      distThead.innerHTML = `
        <tr>
          <th>Column</th>
          <th>Count</th>
          <th>Min</th>
          <th>Max</th>
          <th>Mean</th>
          <th>Median</th>
          <th>Std dev</th>
          <th>25%</th>
          <th>75%</th>
          <th>IQR</th>
          <th>Skew</th>
          <th style="text-align:center;">Action</th>
        </tr>
      `;

      distTbody.innerHTML = numEntries
        .map(([col, d]) => {
          const isSelected = col === activeEdaColumn;
          const iqrVal = d.iqr !== undefined ? d.iqr : d.p75 - d.p25;
          return `
            <tr class="clickable-row ${isSelected ? "active-row" : ""}" data-column="${escapeHtml(col)}" title="Click to view distribution plots for ${escapeHtml(col)}">
              <td class="mono font-bold">${escapeHtml(col)}</td>
              <td>${d.count ? Number(d.count).toLocaleString() : "—"}</td>
              <td>${formatNumber(d.min)}</td>
              <td>${formatNumber(d.max)}</td>
              <td>${formatNumber(d.mean)}</td>
              <td>${formatNumber(d.median)}</td>
              <td>${formatNumber(d.std)}</td>
              <td>${formatNumber(d.p25)}</td>
              <td>${formatNumber(d.p75)}</td>
              <td>${formatNumber(iqrVal)}</td>
              <td>${formatNumber(d.skew !== undefined ? d.skew : 0)}</td>
              <td style="text-align:center;">
                <button type="button" class="btn btn-sm" style="padding:2px 8px;font-size:11px;" data-btn-plot="${escapeHtml(col)}">
                  📈 Plot
                </button>
              </td>
            </tr>
          `;
        })
        .join("");

      // Add click listeners to rows and plot buttons
      distTbody.querySelectorAll("tr.clickable-row").forEach((row) => {
        row.addEventListener("click", () => {
          const colName = row.dataset.column;
          if (colName) renderEdaDistributionPlot(colName);
        });
      });

      distTbody.querySelectorAll("button[data-btn-plot]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          const colName = btn.dataset.btnPlot;
          if (colName) renderEdaDistributionPlot(colName);
        });
      });

      // Auto-plot selected or first column
      const colToPlot = activeEdaColumn && eda.distributions[activeEdaColumn] ? activeEdaColumn : numEntries[0][0];
      if (colToPlot) {
        renderEdaDistributionPlot(colToPlot);
      }
    }

    // 2. Categorical distributions
    const catEl = document.getElementById("eda-categorical-charts") || document.getElementById("eda-categorical");
    if (catEl) {
      const catEntries = Object.entries(eda.categorical_frequencies || {});
      if (catEntries.length === 0) {
        catEl.innerHTML = '<div class="card" style="grid-column: 1 / -1; box-shadow:none;"><p class="small muted">No categorical columns detected in this dataset.</p></div>';
      } else {
        catEl.innerHTML = catEntries
          .map(([col, data], idx) => {
            const freqs = (data && typeof data === "object" && data.counts) ? data.counts : (data || {});
            const total = (data && data.total) || Object.values(freqs).reduce((a, b) => a + Number(b), 0);
            const distinctCount = (data && data.unique_count) || Object.keys(freqs).length;
            const chartId = `eda-cat-chart-${idx}`;

            const rows = Object.entries(freqs)
              .map(([k, v]) => {
                const count = Number(v);
                const pct = total > 0 ? ((count / total) * 100).toFixed(1) : "0.0";
                return `
                  <tr>
                    <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis;" title="${escapeHtml(k)}">${escapeHtml(k)}</td>
                    <td style="text-align:right;">${count.toLocaleString()}</td>
                    <td style="text-align:right;width:110px;">
                      <div style="display:flex;align-items:center;gap:6px;justify-content:flex-end;">
                        <div style="flex:1;height:6px;background:var(--line-soft);border-radius:3px;overflow:hidden;min-width:40px;">
                          <div style="width:${pct}%;height:100%;background:var(--teal);border-radius:3px;"></div>
                        </div>
                        <span class="mono small muted" style="min-width:38px;">${pct}%</span>
                      </div>
                    </td>
                  </tr>
                `;
              })
              .join("");

            return `
              <div class="card" style="box-shadow:none;margin-bottom:0;">
                <div class="card-title">
                  <span>${escapeHtml(col)}</span>
                  <span class="badge badge-neutral" style="font-size:10px;text-transform:none;">${distinctCount} unique</span>
                </div>
                <div id="${chartId}" style="height:170px;margin-bottom:10px;"></div>
                <div class="table-scroll" style="max-height:160px;">
                  <table class="data-table">
                    <thead><tr><th>Value</th><th style="text-align:right;">Count</th><th style="text-align:right;">Share</th></tr></thead>
                    <tbody>${rows}</tbody>
                  </table>
                </div>
              </div>
            `;
          })
          .join("");

        // Render Plotly bar charts for each categorical column
        catEntries.forEach(([col, data], idx) => {
          const freqs = (data && typeof data === "object" && data.counts) ? data.counts : (data || {});
          const chartId = `eda-cat-chart-${idx}`;
          const chartContainer = document.getElementById(chartId);
          if (chartContainer && typeof Plotly !== "undefined") {
            const entries = Object.entries(freqs);
            const sorted = [...entries].reverse(); // reverse so highest is on top in horizontal bar
            Plotly.newPlot(
              chartId,
              [
                {
                  y: sorted.map((e) => (e[0].length > 18 ? e[0].slice(0, 16) + "…" : e[0])),
                  x: sorted.map((e) => Number(e[1])),
                  type: "bar",
                  orientation: "h",
                  marker: {
                    color: sorted.map((_, i) => EDA_PALETTE[i % EDA_PALETTE.length]),
                    line: { width: 0 },
                  },
                  hovertemplate: "<b>%{y}</b><br>Count: <b>%{x:,}</b><extra></extra>",
                },
              ],
              {
                margin: { t: 5, l: 85, r: 15, b: 25 },
                height: 170,
                font: { family: "IBM Plex Sans, sans-serif", size: 10, color: "#1a2226" },
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                xaxis: { automargin: true, gridcolor: "rgba(0,0,0,0.05)" },
                yaxis: { automargin: true },
              },
              { displayModeBar: false, responsive: true }
            );
          }
        });
      }
    }

    // 3. Correlation matrix heatmap
    const corrEl = document.getElementById("eda-correlation");
    if (corrEl) {
      const columns = Object.keys(eda.correlation || {});
      if (columns.length >= 2) {
        if (typeof Plotly === "undefined") {
          corrEl.innerHTML = '<p class="small muted">Plotly visualization library unavailable.</p>';
        } else {
          const z = columns.map((rowCol) => columns.map((colCol) => eda.correlation[rowCol][colCol]));
          const text = z.map((row) => row.map((val) => (val !== null && val !== undefined ? Number(val).toFixed(2) : "0.00")));
          Plotly.newPlot(
            "eda-correlation",
            [
              {
                z,
                x: columns,
                y: columns,
                text,
                texttemplate: "%{text}",
                textfont: { family: "IBM Plex Mono, monospace", size: 10, color: "#1a2226" },
                type: "heatmap",
                colorscale: "RdBu",
                reversescale: true,
                zmin: -1,
                zmax: 1,
                hovertemplate: "<b>%{y}</b> × <b>%{x}</b><br>Correlation: <b>%{z:.3f}</b><extra></extra>",
              },
            ],
            {
              margin: { t: 20, l: 100, r: 30, b: 100 },
              height: Math.max(380, Math.min(650, columns.length * 42 + 100)),
              font: { family: "IBM Plex Sans, sans-serif", size: 11, color: "#1a2226" },
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              xaxis: { automargin: true, tickangle: -30 },
              yaxis: { automargin: true },
              hoverlabel: { font: { family: "IBM Plex Sans, sans-serif", size: 12 }, bgcolor: "#12181c", bordercolor: "#12181c" },
            },
            {
              displayModeBar: "hover",
              responsive: true,
              displaylogo: false,
              modeBarButtonsToRemove: ["lasso2d"],
              toImageButtonOptions: { format: "png", filename: "eda-correlation-heatmap", height: 600, width: 800, scale: 2 },
            }
          );
        }
      } else {
        corrEl.innerHTML = '<p class="small muted">At least 2 numeric columns are required for a correlation heatmap.</p>';
      }
    }
  } catch (err) {
    showError(err);
  }
}

function renderEdaDistributionPlot(colName) {
  activeEdaColumn = colName;
  if (!currentEdaData || !currentEdaData.distributions || !currentEdaData.distributions[colName]) return;

  const d = currentEdaData.distributions[colName];
  const wrapper = document.getElementById("eda-distribution-plot-wrapper");
  const titleEl = document.getElementById("eda-distribution-plot-title");

  if (wrapper) wrapper.style.display = "block";
  if (titleEl) {
    const iqrVal = d.iqr !== undefined ? d.iqr : d.p75 - d.p25;
    titleEl.innerHTML = `Distribution of <span class="mono" style="color:var(--teal);">${escapeHtml(
      colName
    )}</span> <span class="badge badge-neutral" style="font-weight:normal;margin-left:8px;text-transform:none;">Min: ${formatNumber(
      d.min
    )} | Mean: ${formatNumber(d.mean)} | Median: ${formatNumber(d.median)} | Max: ${formatNumber(
      d.max
    )} | Std: ${formatNumber(d.std)} | IQR: ${formatNumber(iqrVal)}</span>`;
  }

  // Update active row class in table
  document.querySelectorAll("#eda-distributions-table tbody tr").forEach((row) => {
    row.classList.toggle("active-row", row.dataset.column === colName);
  });

  if (typeof Plotly === "undefined") return;

  const values = d.values || [];
  const baseLayout = {
    font: { family: "IBM Plex Sans, sans-serif", size: 11, color: "#1a2226" },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    margin: { t: 30, l: 50, r: 20, b: 40 },
    height: 270,
  };
  const config = { displayModeBar: "hover", responsive: true, displaylogo: false };

  // 1. Histogram
  Plotly.newPlot(
    "eda-distribution-histogram",
    [
      {
        x: values.length ? values : [d.min, d.p25, d.median, d.p75, d.max],
        type: "histogram",
        name: "Frequency",
        marker: {
          color: "#2f6f6b",
          line: { color: "#ffffff", width: 1 },
        },
        hovertemplate: "Range: <b>%{x}</b><br>Count: <b>%{y:,}</b><extra></extra>",
      },
    ],
    {
      ...baseLayout,
      title: { text: "Histogram & Frequency Distribution", font: { size: 12, family: "IBM Plex Sans" } },
      xaxis: { title: colName, automargin: true, gridcolor: "rgba(0,0,0,0.06)" },
      yaxis: { title: "Count", automargin: true, gridcolor: "rgba(0,0,0,0.06)" },
    },
    config
  );

  // 2. Box Plot
  Plotly.newPlot(
    "eda-distribution-box",
    [
      {
        y: values.length ? values : [d.min, d.p25, d.median, d.p75, d.max],
        type: "box",
        name: colName,
        boxpoints: "outliers",
        boxmean: true,
        marker: { color: "#d69a2d", size: 4 },
        line: { color: "#b97e17" },
        fillcolor: "rgba(214, 154, 45, 0.2)",
        hovertemplate: "<b>%{y}</b><extra></extra>",
      },
    ],
    {
      ...baseLayout,
      title: { text: "Box & Whisker Plot (Outliers & Quartiles)", font: { size: 12, family: "IBM Plex Sans" } },
      xaxis: { automargin: true },
      yaxis: { title: colName, automargin: true, gridcolor: "rgba(0,0,0,0.06)" },
    },
    config
  );
}

function insightIcon(type) {
  return { trend: "↗", top_performer: "★", concentration: "◎", rate_anomaly: "!", correlation: "⇄", recommendation: "→", info: "i" }[
    type
  ] || "•";
}

async function loadInsightsScreen() {
  if (!requireDataset()) return;
  try {
    const datasetId = AppState.datasetId;
    const result = await apiFetch(`/api/analytics/${datasetId}/insights`);
    if (datasetId !== AppState.datasetId) return;
    const listEl = document.getElementById("insights-list");
    listEl.innerHTML = result.insights
      .map(
        (i) => `
      <div class="insight-item ${i.type === "recommendation" ? "recommendation" : ""}">
        <div class="insight-icon">${insightIcon(i.type)}</div>
        <div><div class="insight-title">${escapeHtml(i.title)}</div><div class="insight-message">${escapeHtml(
          i.message
        )}</div></div>
      </div>`
      )
      .join("");
  } catch (err) {
    showError(err);
  }
}

const SEGMENT_COLORS = ["#2f6f6b", "#d69a2d", "#b5432e", "#5b6a68", "#34785a", "#8a6fb0"];

async function loadSegmentationScreen(useMapping = false) {
  if (!requireDataset()) return;
  const rfmEl = document.getElementById("rfm-content");
  const kmeansEl = document.getElementById("kmeans-content");
  rfmEl.innerHTML = '<span class="spinner"></span>';
  kmeansEl.innerHTML = '<span class="spinner"></span>';

  try {
    const datasetId = AppState.datasetId;
    const params = new URLSearchParams();
    if (useMapping === true) for (const role of ["customer", "date", "amount"]) {
      const value = document.getElementById(`segment-${role}`)?.value;
      if (value) params.set(`${role}_column`, value);
    }
    const result = await apiFetch(`/api/analytics/${datasetId}/segmentation?${params}`);
    if (datasetId !== AppState.datasetId) return;
    document.getElementById("segmentation-mappings").innerHTML = ["customer", "date", "amount"].map(role => `<label>${role} <select id="segment-${role}"><option value="">Auto-detect</option>${result.columns.map(c => `<option value="${escapeHtml(c)}" ${result.selected_mapping[role] === c ? "selected" : ""}>${escapeHtml(c)}</option>`).join("")}</select></label>`).join(" ");

    document.getElementById("rfm-donut-chart").innerHTML = "";
    document.getElementById("kmeans-cluster-chart").innerHTML = "";
    document.getElementById("kmeans-scatter-chart").innerHTML = "";
    if (result.rfm && result.rfm.eligible) {
      const total = Object.values(result.rfm.segment_counts).reduce((a, b) => a + b, 0);
      const bars = Object.entries(result.rfm.segment_counts)
        .map(([seg, count], idx) => {
          const pct = ((count / total) * 100).toFixed(1);
          return `<div class="segment-bar-fill" style="width:${pct}%;background:${SEGMENT_COLORS[idx % SEGMENT_COLORS.length]}" title="${escapeHtml(seg)}: ${count}"></div>`;
        })
        .join("");
      const legend = Object.entries(result.rfm.segment_counts)
        .map(
          ([seg, count], idx) =>
            `<span class="badge" style="background:${SEGMENT_COLORS[idx % SEGMENT_COLORS.length]}22;color:${SEGMENT_COLORS[idx % SEGMENT_COLORS.length]};margin-right:8px;">${escapeHtml(
              seg
            )} · ${count}</span>`
        )
        .join("");
      rfmEl.innerHTML = `<div class="segment-bar-track">${bars}</div><div style="margin-top:10px;">${legend}</div>`;
      if (typeof Plotly !== "undefined") Plotly.newPlot("rfm-donut-chart", [{type:"pie", hole:0.5, labels:Object.keys(result.rfm.segment_counts), values:Object.values(result.rfm.segment_counts)}], {height:250, margin:{t:15,b:15}}, {responsive:true,displayModeBar:false});
    } else {
      rfmEl.innerHTML = `<p class="small muted">${escapeHtml(
        (result.rfm && result.rfm.reason) || "RFM segmentation is not available for this dataset."
      )}</p>`;
    }

    if (result.kmeans && result.kmeans.eligible) {
      const rows = Object.entries(result.kmeans.cluster_sizes)
        .map(
          ([cluster, size]) =>
            `<tr><td>${escapeHtml(result.kmeans.segment_names[cluster] || `Cluster ${cluster}`)}</td><td>${size}</td></tr>`
        )
        .join("");
      kmeansEl.innerHTML = `<p class="small muted">Features used: ${result.kmeans.features_used
        .map(escapeHtml)
        .join(", ")}</p><table class="data-table"><thead><tr><th>Segment</th><th>Rows</th></tr></thead><tbody>${rows}</tbody></table>`;
      if (typeof Plotly !== "undefined") Plotly.newPlot("kmeans-cluster-chart", [{type:"bar", x:Object.keys(result.kmeans.cluster_sizes).map(k => result.kmeans.segment_names[k]), y:Object.values(result.kmeans.cluster_sizes), marker:{color:SEGMENT_COLORS}}], {height:250, margin:{t:15,b:70}, yaxis:{title:"Rows"}}, {responsive:true, displayModeBar:false});
      const scatter = result.kmeans.scatter;
      kmeansEl.innerHTML += `<p class="small muted">${escapeHtml(result.kmeans.visualization_note)} Rows used: ${result.kmeans.rows_used}; excluded: ${result.kmeans.rows_excluded}.</p>`;
      if (typeof Plotly !== "undefined" && scatter) {
        await Plotly.newPlot("kmeans-scatter-chart", Object.keys(result.kmeans.cluster_sizes).map((cluster, i) => {
          const points = scatter.points.filter(p => String(p.cluster) === cluster);
          return {type:"scatter", mode:"markers", name:`Cluster ${cluster}`, x:points.map(p => p[scatter.x]), y:points.map(p => p[scatter.y]), marker:{color:SEGMENT_COLORS[i % SEGMENT_COLORS.length], opacity:0.65}};
        }), {height:320, margin:{t:20,b:60,l:60}, xaxis:{title:{text:scatter.x}}, yaxis:{title:{text:scatter.y}}}, {responsive:true,displayModeBar:false});
      } else if (typeof Plotly === "undefined") {
        kmeansEl.innerHTML += '<p>Plotly is unavailable. Cluster counts and means are shown in the tables.</p>';
      }
      kmeansEl.innerHTML += `<div class="table-scroll"><table class="data-table"><thead><tr><th>Segment mean</th>${result.kmeans.features_used.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead><tbody>${Object.entries(result.kmeans.cluster_profile).map(([k, values]) => `<tr><td>${escapeHtml(result.kmeans.segment_names[k])}</td>${result.kmeans.features_used.map(c => `<td>${formatNumber(values[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;

    } else {
      kmeansEl.innerHTML = `<p class="small muted">${escapeHtml(
        (result.kmeans && result.kmeans.reason) || "K-Means segmentation is not available for this dataset."
      )}</p>`;
    }
  } catch (err) {
    rfmEl.textContent = err.message; kmeansEl.textContent = err.message;
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  registerScreenHandler("eda", loadEdaScreen);
  registerScreenHandler("insights", loadInsightsScreen);
  registerScreenHandler("segmentation", loadSegmentationScreen);

  const closeBtn = document.getElementById("btn-close-eda-plot");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      const wrapper = document.getElementById("eda-distribution-plot-wrapper");
      if (wrapper) wrapper.style.display = "none";
      activeEdaColumn = null;
      document.querySelectorAll("#eda-distributions-table tbody tr").forEach((row) => {
        row.classList.remove("active-row");
      });
    });
  }
});
