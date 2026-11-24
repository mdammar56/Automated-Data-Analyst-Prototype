/**
 * frontend/js/upload.js
 * Dataset Upload and Validation screen (Section 12).
 */

async function handleFileUpload(file) {
  const statusEl = document.getElementById("upload-status");
  statusEl.innerHTML = '<span class="spinner"></span> Uploading and validating…';

  const formData = new FormData();
  formData.append("file", file);

  try {
    const result = await apiFetch("/api/upload", { method: "POST", body: formData });

    setDataset(result.dataset_id, result.filename);

    statusEl.textContent = `Uploaded "${result.filename}" successfully.`;
    showToast(`Dataset uploaded: ${result.filename}`, "success");

    document.getElementById("recent-upload-card").style.display = "block";
    document.getElementById("upload-summary").innerHTML = `
      <div class="kpi-card"><div class="kpi-label">Filename</div><div class="kpi-value" style="font-size:14px;">${escapeHtml(result.filename)}</div></div>
      <div class="kpi-card"><div class="kpi-label">Size</div><div class="kpi-value" style="font-size:16px;">${(result.size_bytes / 1024).toFixed(1)} KB</div></div>
      <div class="kpi-card"><div class="kpi-label">Rows</div><div class="kpi-value">${result.rows.toLocaleString()}</div></div>
      <div class="kpi-card"><div class="kpi-label">Columns</div><div class="kpi-value">${result.columns}</div></div>
    `;
  } catch (err) {
    statusEl.textContent = "";
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const dropZone = document.getElementById("upload-drop");
  const fileInput = document.getElementById("file-input");

  dropZone.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) handleFileUpload(fileInput.files[0]);
  });

  ["dragenter", "dragover"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.add("drag-over");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-over");
    })
  );
  dropZone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) handleFileUpload(e.dataTransfer.files[0]);
  });


});
