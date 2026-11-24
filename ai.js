/**
 * frontend/js/ai.js
 * Optional Gemini "Ask Your Data" screen (Section 29). Works gracefully with
 * a clear message when AI mode is disabled.
 */

async function askYourData() {
  const question = document.getElementById("ai-question").value.trim();
  const tableName = document.getElementById("ai-table-name").value.trim();
  if (!question) {
    showToast("Type a question first.", "error");
    return;
  }

  const datasetId = AppState.datasetId;
  const btn = document.getElementById("btn-ask-ai");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Thinking…';

  try {
    const result = await apiFetch("/api/ai/ask", {
      method: "POST",
      body: { dataset_id: AppState.datasetId, table_name: tableName || undefined, question, scope: document.getElementById("ai-scope")?.value || "project" },
    });

    if (datasetId !== AppState.datasetId) return;
    document.getElementById("ai-answer-card").style.display = "block";
    document.getElementById("ai-answer-text").textContent = result.answer;
    document.getElementById("ai-answer-sql").textContent = result.sql || "";
  } catch (err) {
    showError(err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Ask";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-ask-ai").addEventListener("click", askYourData);
});
