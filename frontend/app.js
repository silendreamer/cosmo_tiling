const form = document.querySelector("#converter-form");
const fileInput = document.querySelector("#pdf-file");
const dropZone = document.querySelector("#drop-zone");
const fileCard = document.querySelector("#file-card");
const fileName = document.querySelector("#file-name");
const fileSize = document.querySelector("#file-size");
const fileError = document.querySelector("#file-error");
const removeFileButton = document.querySelector("#remove-file");
const convertButton = document.querySelector("#convert-button");
const templateInputs = Array.from(form.querySelectorAll('input[name="template"]'));
const templateError = document.querySelector("#template-error");
const buttonLabel = convertButton.querySelector(".button-label");
const statusMessage = document.querySelector("#status-message");
const statusTitle = document.querySelector("#status-title");
const statusDetail = document.querySelector("#status-detail");
const downloadLink = document.querySelector("#download-link");
const historyBody = document.querySelector("#history-body");
const historyCount = document.querySelector("#history-count");
const historyEmpty = document.querySelector("#history-empty");
const historyLoading = document.querySelector("#history-loading");
const historyError = document.querySelector("#history-error");
const historyRetry = document.querySelector("#history-retry");
const historyTableWrap = document.querySelector("#history-table-wrap");
const historyFooter = document.querySelector("#history-footer");
const historyLoadMore = document.querySelector("#history-load-more");

const MAX_FILE_SIZE = 4 * 1024 * 1024;
const HISTORY_PAGE_SIZE = 50;
let selectedFile = null;
let conversionIsBusy = false;
let currentDownloadUrl = null;
let historyOffset = 0;
let historyTotal = 0;
let historyHasMore = false;
let historyIsLoading = false;
const historyIds = new Set();

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTimestamp(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown date";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function showError(message) {
  fileError.textContent = message;
  fileError.hidden = false;
  dropZone.classList.add("has-error");
}

function clearError() {
  fileError.hidden = true;
  fileError.textContent = "";
  dropZone.classList.remove("has-error");
}

function selectedTemplate() {
  return templateInputs.find((input) => input.checked)?.value || "";
}

function clearTemplateError() {
  templateError.hidden = true;
  templateError.textContent = "";
}

function updateConvertButtonState() {
  convertButton.disabled = conversionIsBusy || !selectedFile || !selectedTemplate();
}

function resetTemplateSelection() {
  templateInputs.forEach((input) => {
    input.checked = false;
  });
  clearTemplateError();
  updateConvertButtonState();
}

function clearDownload() {
  if (currentDownloadUrl) URL.revokeObjectURL(currentDownloadUrl);
  currentDownloadUrl = null;
  downloadLink.hidden = true;
  downloadLink.removeAttribute("download");
  downloadLink.href = "#";
}

function resetFilePicker() {
  selectedFile = null;
  fileInput.value = "";
  fileCard.hidden = true;
  dropZone.hidden = false;
  clearError();
  updateConvertButtonState();
}

function templateLabel(template) {
  if (template === "classica") return "Classica";
  if (template === "saussy") return "Saussy";
  return template || "Unknown";
}

function updateHistoryState() {
  historyCount.textContent = `${historyTotal} ${historyTotal === 1 ? "file" : "files"}`;
  const hasRows = historyIds.size > 0;
  historyTableWrap.hidden = !hasRows;
  historyEmpty.hidden = historyIsLoading || hasRows || !historyError.hidden;
  historyFooter.hidden = !historyHasMore || historyIsLoading;
  historyLoadMore.disabled = historyIsLoading;
}

function createHistoryRow(record) {
  const row = document.createElement("tr");
  row.dataset.conversionId = record.id;
  const dateCell = document.createElement("td");
  const time = document.createElement("time");
  time.dateTime = record.created_at_utc;
  time.textContent = formatTimestamp(record.created_at_utc);
  dateCell.append(time);

  const fileCell = document.createElement("td");
  const fileText = document.createElement("span");
  fileText.className = "history-file-name";
  fileText.textContent = record.status === "success"
    ? record.output_filename || record.source_filename
    : record.source_filename;
  fileCell.append(fileText);

  const templateCell = document.createElement("td");
  templateCell.textContent = templateLabel(record.template);
  const statusCell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `status-badge is-${record.status}`;
  badge.textContent = record.status === "success" ? "Success" : "Failed";
  statusCell.append(badge);

  const detailsCell = document.createElement("td");
  detailsCell.className = "history-details";
  if (record.status === "failed") {
    detailsCell.textContent = record.failure_reason || "No reason was provided.";
  } else {
    const hasCount = record.row_count !== null && record.row_count !== "" && record.row_count !== undefined;
    const count = Number(record.row_count);
    detailsCell.textContent = hasCount && Number.isFinite(count) ? `${count} order ${count === 1 ? "row" : "rows"}` : "Workbook created";
  }
  row.append(dateCell, fileCell, templateCell, statusCell, detailsCell);
  return row;
}

function addHistoryRecords(records, { prepend = false } = {}) {
  const fragment = document.createDocumentFragment();
  records.forEach((record) => {
    if (!record || !record.id || historyIds.has(record.id)) return;
    historyIds.add(record.id);
    fragment.append(createHistoryRow(record));
  });
  if (prepend) historyBody.prepend(fragment);
  else historyBody.append(fragment);
}

async function loadHistory({ reset = false } = {}) {
  if (historyIsLoading) return;
  historyIsLoading = true;
  historyError.hidden = true;
  historyLoading.hidden = !reset && historyIds.size > 0;
  historyLoadMore.textContent = "Loading…";
  if (reset) {
    historyOffset = 0;
    historyTotal = 0;
    historyHasMore = false;
    historyIds.clear();
    historyBody.replaceChildren();
  }
  updateHistoryState();
  try {
    const response = await fetch(`/api/conversions?limit=${HISTORY_PAGE_SIZE}&offset=${historyOffset}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("History request failed");
    const page = await response.json();
    if (!Array.isArray(page.items)) throw new Error("History response was invalid");
    addHistoryRecords(page.items);
    historyOffset += page.items.length;
    historyTotal = Number(page.total) || 0;
    historyHasMore = Boolean(page.has_more);
  } catch (_error) {
    historyError.hidden = false;
  } finally {
    historyIsLoading = false;
    historyLoading.hidden = true;
    historyLoadMore.textContent = "Load more";
    updateHistoryState();
  }
}

function hideStatus() {
  statusMessage.hidden = true;
  statusMessage.className = "status-message";
  statusMessage.setAttribute("role", "status");
}

function showStatus(state, title, detail) {
  statusMessage.className = `status-message is-${state}`;
  statusMessage.setAttribute("role", state === "error" ? "alert" : "status");
  statusTitle.textContent = title;
  statusDetail.textContent = detail;
  statusMessage.hidden = false;
}

function setBusy(isBusy) {
  conversionIsBusy = isBusy;
  form.setAttribute("aria-busy", String(isBusy));
  updateConvertButtonState();
  buttonLabel.textContent = isBusy ? "Creating workbook…" : "Convert to Excel";
  templateInputs.forEach((input) => {
    input.disabled = isBusy;
  });
  removeFileButton.disabled = isBusy;
  convertButton.classList.toggle("is-loading", isBusy);
}

function outputFilename(pdfName) {
  return `${pdfName.slice(0, -4)}.xlsx`;
}

async function readErrorResponse(response) {
  let body = null;
  try {
    body = await response.json();
    if (typeof body.detail === "string") return { message: body.detail, body };
    if (Array.isArray(body.detail)) {
      const detail = body.detail.map((item) => item.msg).filter(Boolean).join(" ");
      if (detail) return { message: detail, body };
    }
  } catch (_error) {
    // Platform errors can be HTML or empty; use a safe message below.
  }
  if (response.status === 404) return { message: "The conversion service is not available in this deployment. Contact the administrator.", body };
  if (response.status === 413) return { message: "This file is too large for the web converter. Choose a PDF under 4 MB.", body };
  if (response.status === 504) return { message: "The conversion took too long. Try the file again or contact the administrator.", body };
  if (response.status >= 500) return { message: "The conversion service encountered an error. Try again or contact the administrator.", body };
  return { message: "The workbook could not be created. Check the PDF and template, then try again.", body };
}

function clearFile() {
  resetFilePicker();
  clearDownload();
  hideStatus();
}

function selectFile(file) {
  clearError();
  clearDownload();
  hideStatus();
  if (!file) return;
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return showError("Choose a PDF file to continue.");
  if (file.size > MAX_FILE_SIZE) return showError("This PDF is larger than 4 MB. Choose a smaller file.");
  selectedFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = `${formatFileSize(file.size)} · PDF document`;
  dropZone.hidden = true;
  fileCard.hidden = false;
  updateConvertButtonState();
}

fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));
removeFileButton.addEventListener("click", clearFile);
templateInputs.forEach((input) => {
  input.addEventListener("change", () => {
    clearTemplateError();
    updateConvertButtonState();
  });
});
historyRetry.addEventListener("click", () => loadHistory({ reset: true }));
historyLoadMore.addEventListener("click", () => loadHistory());

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  });
});

dropZone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFile) {
    showError("Upload a PDF before starting the conversion.");
    dropZone.focus();
    return;
  }
  const attemptedTemplate = selectedTemplate();
  if (!attemptedTemplate) {
    templateError.textContent = "Choose either the Saussy or Classica template.";
    templateError.hidden = false;
    templateInputs[0].focus();
    updateConvertButtonState();
    return;
  }
  clearDownload();
  setBusy(true);
  showStatus("processing", "Creating your workbook", "Reading the PDF and preparing the Excel file. This may take a moment.");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  statusMessage.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
  const attemptedFile = selectedFile;
  const data = new FormData();
  data.append("pdf", attemptedFile, attemptedFile.name);
  data.append("template", attemptedTemplate);

  try {
    const response = await fetch("/api/convert", { method: "POST", body: data });
    if (!response.ok) {
      const failure = await readErrorResponse(response);
      if (failure.body?.conversion) {
        addHistoryRecords([failure.body.conversion], { prepend: true });
        historyTotal += 1;
        historyOffset += 1;
        updateHistoryState();
      }
      const archiveNote = failure.body?.history_saved === false ? " This failure was not added to shared history." : "";
      throw new Error(`${failure.message}${archiveNote}`);
    }

    const workbook = await response.blob();
    const filename = outputFilename(attemptedFile.name);
    currentDownloadUrl = URL.createObjectURL(workbook);
    downloadLink.href = currentDownloadUrl;
    downloadLink.download = filename;
    downloadLink.hidden = false;
    const historySaved = response.headers.get("X-History-Saved") === "true";
    if (historySaved) {
      addHistoryRecords([{
        id: response.headers.get("X-Conversion-Id"),
        source_filename: attemptedFile.name,
        output_filename: filename,
        template: attemptedTemplate,
        status: "success",
        failure_reason: "",
        row_count: Number(response.headers.get("X-Order-Row-Count")),
        created_at_utc: response.headers.get("X-Conversion-Created-At"),
      }], { prepend: true });
      historyTotal += 1;
      historyOffset += 1;
      updateHistoryState();
    }
    const detail = historySaved
      ? filename
      : `${filename} — ready to download, but it was not added to shared history.`;
    showStatus("success", "Your workbook is ready", detail);
    resetFilePicker();
    resetTemplateSelection();
    downloadLink.focus();
  } catch (error) {
    const message = error instanceof TypeError
      ? "The converter could not be reached. Check your connection and try again."
      : error instanceof Error
        ? error.message
        : "The conversion failed. Please try again.";
    showStatus("error", "Could not create the workbook", message);
  } finally {
    setBusy(false);
  }
});

window.addEventListener("beforeunload", () => {
  if (currentDownloadUrl) URL.revokeObjectURL(currentDownloadUrl);
});

loadHistory({ reset: true });
