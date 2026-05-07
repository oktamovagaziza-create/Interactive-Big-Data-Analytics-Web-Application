const dropZone = document.querySelector("#dropZone");
const fileInput = document.querySelector("#fileInput");
const browseButton = document.querySelector("#browseButton");
const fileMeta = document.querySelector("#fileMeta");
const analyzeButton = document.querySelector("#analyzeButton");
const previewPanel = document.querySelector("#previewPanel");
const previewTable = document.querySelector("#previewTable");
const loading = document.querySelector("#loading");
const errorBox = document.querySelector("#errorBox");
const results = document.querySelector("#results");

let selectedFile = null;

browseButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (event) => chooseFile(event.target.files[0]));

["dragenter", "dragover"].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});

dropZone.addEventListener("drop", (event) => chooseFile(event.dataTransfer.files[0]));
analyzeButton.addEventListener("click", analyzeDataset);

function chooseFile(file) {
  clearError();
  if (!file) return;
  if (!/\.(csv|xlsx|xls)$/i.test(file.name)) {
    showError("Only CSV and Excel files are supported.");
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    showError("File exceeds the 50 MB upload limit.");
    return;
  }
  selectedFile = file;
  fileMeta.textContent = `${file.name} • ${formatBytes(file.size)}`;
  previewPanel.classList.add("hidden");
  results.classList.add("hidden");
  renderLocalPreview(file);
}

async function renderLocalPreview(file) {
  if (!file.name.toLowerCase().endsWith(".csv")) {
    previewTable.innerHTML = "<tbody><tr><td>Excel preview will appear after analysis.</td></tr></tbody>";
    previewPanel.classList.remove("hidden");
    return;
  }
  const text = await file.text();
  const rows = parseCsvPreview(text).slice(0, 21);
  renderTable(rows[0] || [], rows.slice(1));
  previewPanel.classList.remove("hidden");
}

async function analyzeDataset() {
  if (!selectedFile) {
    showError("Choose a dataset first.");
    return;
  }
  clearError();
  loading.classList.remove("hidden");
  results.classList.add("hidden");
  analyzeButton.disabled = true;

  const form = new FormData();
  form.append("file", selectedFile);

  try {
    const response = await fetch("/api/analyze", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Analysis failed.");
    renderAnalysis(payload);
  } catch (error) {
    showError(error.message);
  } finally {
    loading.classList.add("hidden");
    analyzeButton.disabled = false;
  }
}

function renderAnalysis(data) {
  renderTable(data.preview.columns, data.preview.rows.map((row) => data.preview.columns.map((col) => row[col])));
  renderMetrics(data);
  renderColumnTypes(data.summary.column_types);
  renderCorrelations(data.statistics.top_correlations);
  renderOutliers(data.statistics.outliers);
  renderInsights(data.insights, data.conclusions);
  renderCharts(data.visualizations);
  previewPanel.classList.remove("hidden");
  results.classList.remove("hidden");
}

function renderTable(columns, rows) {
  const head = `<thead><tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead>`;
  const body = `<tbody>${rows
    .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell ?? "")}</td>`).join("")}</tr>`)
    .join("")}</tbody>`;
  previewTable.innerHTML = head + body;
}

function renderMetrics(data) {
  const [rows, columns] = data.summary.cleaned_shape;
  const chartCount = data.visualizations.length;
  const missing = Object.values(data.summary.cleaned_missing_values).reduce((sum, value) => sum + value, 0);
  document.querySelector("#metrics").innerHTML = [
    metric(rows.toLocaleString(), "Cleaned rows"),
    metric(columns.toLocaleString(), "Cleaned columns"),
    metric(chartCount.toLocaleString(), "Visualizations"),
    metric(missing.toLocaleString(), "Remaining missing values"),
  ].join("");
}

function metric(value, label) {
  return `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`;
}

function renderColumnTypes(types) {
  document.querySelector("#columnTypes").innerHTML = Object.entries(types)
    .map(([type, cols]) => `<div class="chip"><strong>${type}</strong>: ${cols.length ? cols.join(", ") : "None"}</div>`)
    .join("");
}

function renderCorrelations(items) {
  document.querySelector("#correlations").innerHTML = items.length
    ? items.map((item) => `<div class="list-item"><strong>${item.columns.join(" ↔ ")}</strong><br>r = ${item.correlation}</div>`).join("")
    : '<div class="list-item">No numeric pairs available.</div>';
}

function renderOutliers(items) {
  document.querySelector("#outliers").innerHTML = items.length
    ? items.map((item) => `<div class="list-item"><strong>${item.column}</strong><br>${item.count} rows (${(item.share * 100).toFixed(2)}%)</div>`).join("")
    : '<div class="list-item">No strong z-score outliers detected.</div>';
}

function renderInsights(insights, conclusions) {
  document.querySelector("#insights").innerHTML = insights.map((text) => `<div class="insight">${escapeHtml(text)}</div>`).join("");
  document.querySelector("#conclusions").textContent = conclusions;
}

function renderCharts(charts) {
  const chartsEl = document.querySelector("#charts");
  chartsEl.innerHTML = charts
    .map((chart) => `<article class="chart-card"><h2>${escapeHtml(chart.title)}</h2><p>${escapeHtml(chart.description)}</p><div class="plot" id="chart-${chart.id}"></div></article>`)
    .join("");
  charts.forEach((chart) => {
    Plotly.newPlot(`chart-${chart.id}`, chart.figure.data, chart.figure.layout, { responsive: true, displaylogo: false });
  });
}

function parseCsvPreview(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length && rows.length < 21; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function clearError() {
  errorBox.classList.add("hidden");
  errorBox.textContent = "";
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
