/**
 * frontend/js/app.js
 *
 * Global application state, screen navigation, toast notifications and a
 * thin fetch() wrapper shared by every other frontend module. No build step
 * or framework is used for Version 1 — plain HTML/CSS/JS talking to the
 * FastAPI backend over REST.
 */

const API_BASE =
  window.__API_BASE__ ||
  (window.location.origin && window.location.origin.startsWith("http")
    ? window.location.origin
    : "http://localhost:8000");

const AppState = {
  datasetId: null,
  filename: null,
  columnProfiles: [],
  columnRoles: {},
  columnDtypes: {},
  numericColumns: [],
  categoricalColumns: [],
  dbConfigured: false,
  databaseName: null,
  aiEnabled: false,
};

function setDataset(id, filename) {
  if (AppState.datasetId !== id) {
    AppState.columnProfiles = []; AppState.columnRoles = {}; AppState.columnDtypes = {};
    AppState.numericColumns = []; AppState.categoricalColumns = [];
    AppState.importedTable = null;
    document.getElementById("ai-table-name").value = "";
    document.getElementById("ai-answer-card").style.display = "none";
  }
  AppState.datasetId = id;
  AppState.filename = filename;
  if (id) {
    sessionStorage.setItem("current_dataset_id", id);
    if (filename) sessionStorage.setItem("current_filename", filename);
  } else {
    sessionStorage.removeItem("current_dataset_id");
    sessionStorage.removeItem("current_filename");
  }
  updateSidebarDataset();
}

/* ---------------------------------------------------------------------- */
/* Fetch helper                                                            */
/* ---------------------------------------------------------------------- */

async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const opts = { ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    opts.body = JSON.stringify(opts.body);
  }
  let response;
  try {
    response = await fetch(url, opts);
  } catch (err) {
    throw new Error(
      `Could not reach the backend at ${API_BASE}. Is it running? (uvicorn backend.main:app --reload)`
    );
  }
  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  }
  if (!response.ok) {
    const detail = (payload && (payload.detail || payload.error)) || response.statusText;
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = response.status;
    err.payload = payload;
    throw err;
  }
  return payload;
}

/* ---------------------------------------------------------------------- */
/* Toasts                                                                  */
/* ---------------------------------------------------------------------- */

function showToast(message, type = "info") {
  const stack = document.getElementById("toast-stack");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  stack.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function showError(err) {
  console.error(err);
  showToast(err.message || String(err), "error");
}

/* ---------------------------------------------------------------------- */
/* Navigation                                                              */
/* ---------------------------------------------------------------------- */

const SCREEN_TITLES = {
  upload: "Home / Upload",
  profile: "Dataset Profile",
  cleaning: "Data Cleaning",
  quality: "Data Quality",
  preview: "Data Preview",
  database: "PostgreSQL Setup",
  sql: "SQL Workspace",
  eda: "Exploratory Data Analysis",
  insights: "Insights",
  dashboard: "Dashboard",
  segmentation: "Customer Segmentation",
  ai: "Ask Your Data",
  reports: "Reports",
  settings: "Settings",
};

const SCREEN_ON_ENTER = {};

function registerScreenHandler(screen, handler) {
  SCREEN_ON_ENTER[screen] = handler;
}

function goToScreen(screen) {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.screen === screen);
  });
  document.querySelectorAll(".screen").forEach((section) => {
    section.classList.toggle("active", section.id === `screen-${screen}`);
  });
  document.getElementById("topbar-title").textContent = SCREEN_TITLES[screen] || screen;

  // Keep live health and database status indicators updated across screen transitions
  refreshHealthIndicators();

  if (SCREEN_ON_ENTER[screen]) {
    try {
      Promise.resolve(SCREEN_ON_ENTER[screen]()).catch(showError);
    } catch (err) {
      showError(err);
    }
  }
}

function requireDataset() {
  if (!AppState.datasetId) {
    showToast("Upload a dataset first.", "error");
    goToScreen("upload");
    return false;
  }
  return true;
}

/* ---------------------------------------------------------------------- */
/* Status indicators                                                      */
/* ---------------------------------------------------------------------- */

function updateSidebarDataset() {
  document.getElementById("sidebar-dataset-id").textContent = AppState.datasetId
    ? `${AppState.datasetId} (${AppState.filename || "dataset"})`
    : "none";
}

async function refreshHealthIndicators() {
  let appOnline = false;
  let appStatusText = "offline";
  try {
    const health = await apiFetch("/health");
    appOnline = true;
    appStatusText = health.status || "healthy";
    AppState.dbConfigured = !!health.database_configured;
    AppState.dbConnected = !!health.database_connected;
    AppState.databaseName = health.database_name || null;
    AppState.aiEnabled = !!(health.ai_configured || health.ai_enabled);
    AppState.aiModel = health.ai_model || "gemini-2.5-flash";
  } catch (err) {
    appOnline = false;
    AppState.dbConfigured = false;
    AppState.dbConnected = false;
    AppState.databaseName = null;
    AppState.aiEnabled = false;
  }

  const dbDot = document.getElementById("db-status-dot");
  const dbText = document.getElementById("db-status-text");
  dbDot.className = `status-dot ${AppState.dbConnected ? "ok" : AppState.dbConfigured ? "warn" : "off"}`;
  dbText.textContent = AppState.dbConnected
    ? (AppState.databaseName ? `Connected: ${AppState.databaseName}` : "Database connected")
    : AppState.dbConfigured
      ? "Database configured (offline)"
      : "Database not configured";

  const aiDot = document.getElementById("ai-status-dot");
  const aiText = document.getElementById("ai-status-text");
  aiDot.className = `status-dot ${AppState.aiEnabled ? "ok" : "off"}`;
  aiText.textContent = AppState.aiEnabled ? `AI ready (${AppState.aiModel})` : "AI disabled";

  const settingsApiBase = document.getElementById("settings-api-base");
  if (settingsApiBase) settingsApiBase.textContent = API_BASE;

  const settingsAppStatus = document.getElementById("settings-app-status");
  if (settingsAppStatus) {
    settingsAppStatus.innerHTML = appOnline
      ? `<span class="badge badge-ok">${escapeHtml(appStatusText)}</span>`
      : '<span class="badge badge-danger">offline</span>';
  }

  const settingsDbStatus = document.getElementById("settings-db-status");
  if (settingsDbStatus) {
    settingsDbStatus.innerHTML = AppState.dbConnected
      ? `<span class="badge badge-ok">connected (${escapeHtml(AppState.databaseName || "active")})</span>`
      : AppState.dbConfigured
        ? `<span class="badge badge-warn">configured (${escapeHtml(AppState.databaseName || "unreachable")})</span>`
        : '<span class="badge badge-neutral">not configured</span>';
  }

  const settingsAiStatus = document.getElementById("settings-ai-status");
  if (settingsAiStatus) {
    settingsAiStatus.innerHTML = AppState.aiEnabled
      ? `<span class="badge badge-ok">configured (${escapeHtml(AppState.aiModel)})</span>`
      : '<span class="badge badge-neutral">disabled</span>';
  }
}

/* ---------------------------------------------------------------------- */
/* Formatting helpers shared across modules                                */
/* ---------------------------------------------------------------------- */

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 1000) return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str === null || str === undefined ? "" : String(str);
  return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* ---------------------------------------------------------------------- */
/* Boot                                                                    */
/* ---------------------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", () => {
  const workflow = Object.keys(SCREEN_TITLES).filter(s => s !== "settings");
  workflow.forEach((screen, index) => {
    const footer = document.createElement("div");
    footer.className = "workflow-navigation";
    [["Back", index - 1], ["Next", index + 1]].forEach(([label, target]) => {
      const button = document.createElement("button");
      button.className = label === "Next" ? "btn btn-primary" : "btn";
      button.textContent = label;
      button.disabled = target < 0 || target >= workflow.length;
      button.addEventListener("click", () => goToScreen(workflow[target]));
      footer.appendChild(button);
    });
    document.getElementById(`screen-${screen}`).appendChild(footer);
  });
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => goToScreen(btn.dataset.screen));
  });

  // Restore dataset session if present
  const savedId = sessionStorage.getItem("current_dataset_id");
  const savedFilename = sessionStorage.getItem("current_filename");
  if (savedId) {
    AppState.datasetId = savedId;
    AppState.filename = savedFilename || savedId;
    updateSidebarDataset();
  }

  refreshHealthIndicators();
});

