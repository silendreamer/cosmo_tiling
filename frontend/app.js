const form = document.querySelector("#converter-form");
const orderTypeInputs = Array.from(form.querySelectorAll('input[name="order-type"]'));
const newOrderSection = document.querySelector("#new-order-section");
const correctedOrderSection = document.querySelector("#corrected-order-section");
const fileInput = document.querySelector("#pdf-file");
const dropZone = document.querySelector("#drop-zone");
const fileCard = document.querySelector("#file-card");
const fileName = document.querySelector("#file-name");
const fileSize = document.querySelector("#file-size");
const fileError = document.querySelector("#file-error");
const removeFileButton = document.querySelector("#remove-file");
const originalFileInput = document.querySelector("#original-pdf-file");
const originalDropZone = document.querySelector("#original-drop-zone");
const originalFileCard = document.querySelector("#original-file-card");
const originalFileName = document.querySelector("#original-file-name");
const originalFileSize = document.querySelector("#original-file-size");
const originalFileError = document.querySelector("#original-file-error");
const removeOriginalFileButton = document.querySelector("#remove-original-file");
const correctedFileInput = document.querySelector("#corrected-pdf-file");
const correctedDropZone = document.querySelector("#corrected-drop-zone");
const correctedFileCard = document.querySelector("#corrected-file-card");
const correctedFileName = document.querySelector("#corrected-file-name");
const correctedFileSize = document.querySelector("#corrected-file-size");
const correctedFileError = document.querySelector("#corrected-file-error");
const removeCorrectedFileButton = document.querySelector("#remove-corrected-file");
const convertButton = document.querySelector("#convert-button");
const templateInputs = Array.from(form.querySelectorAll('input[name="template"]'));
const templateError = document.querySelector("#template-error");
const correctionTemplateNote = document.querySelector("#correction-template-note");
const correctionReview = document.querySelector("#correction-review");
const reviewList = document.querySelector("#review-list");
const reviewError = document.querySelector("#review-error");
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
let selectedOriginalFile = null;
let selectedCorrectedFile = null;
let correctionAnalysis = null;
let correctionDecisions = {};
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

function selectedOrderType() {
  return orderTypeInputs.find((input) => input.checked)?.value || "new";
}

function clearTemplateError() {
  templateError.hidden = true;
  templateError.textContent = "";
}

function updateConvertButtonState() {
  const template = selectedTemplate();
  const isCorrected = selectedOrderType() === "corrected";
  const filesReady = isCorrected
    ? selectedOriginalFile && selectedCorrectedFile
    : selectedFile;
  const correctedFilesValid = !isCorrected || !filesReady || (
    selectedOriginalFile.size + selectedCorrectedFile.size <= MAX_FILE_SIZE
    && !(
      selectedOriginalFile.name === selectedCorrectedFile.name
      && selectedOriginalFile.size === selectedCorrectedFile.size
      && selectedOriginalFile.lastModified === selectedCorrectedFile.lastModified
    )
  );
  const correctionTemplateReady = !isCorrected || template === "classica";
  const reviewReady = !correctionAnalysis
    || !correctionAnalysis.requires_review
    || correctionAnalysis.actions
      .filter((action) => action.confidence === "review")
      .every((action) => correctionDecisions[action.id]);
  convertButton.disabled = conversionIsBusy
    || !filesReady
    || !correctedFilesValid
    || !template
    || !correctionTemplateReady
    || !reviewReady;
}

function resetTemplateSelection() {
  templateInputs.forEach((input) => {
    input.checked = false;
  });
  clearTemplateError();
  updateConvertButtonState();
}

function resetCorrectionAnalysis() {
  correctionAnalysis = null;
  correctionDecisions = {};
  reviewList.replaceChildren();
  correctionReview.hidden = true;
  reviewError.hidden = true;
  reviewError.textContent = "";
  buttonLabel.textContent = selectedOrderType() === "corrected"
    ? "Analyze corrections"
    : "Convert to Excel";
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

function clearCorrectedFile(kind) {
  const isOriginal = kind === "original";
  if (isOriginal) {
    selectedOriginalFile = null;
    originalFileInput.value = "";
    originalFileCard.hidden = true;
    originalDropZone.hidden = false;
    originalFileError.hidden = true;
    originalDropZone.classList.remove("has-error");
  } else {
    selectedCorrectedFile = null;
    correctedFileInput.value = "";
    correctedFileCard.hidden = true;
    correctedDropZone.hidden = false;
    correctedFileError.hidden = true;
    correctedDropZone.classList.remove("has-error");
  }
  resetCorrectionAnalysis();
  clearDownload();
  hideStatus();
  updateConvertButtonState();
}

function resetCorrectedFiles() {
  selectedOriginalFile = null;
  selectedCorrectedFile = null;
  originalFileInput.value = "";
  correctedFileInput.value = "";
  originalFileCard.hidden = true;
  correctedFileCard.hidden = true;
  originalDropZone.hidden = false;
  correctedDropZone.hidden = false;
  [originalFileError, correctedFileError].forEach((element) => {
    element.hidden = true;
    element.textContent = "";
  });
  originalDropZone.classList.remove("has-error");
  correctedDropZone.classList.remove("has-error");
  resetCorrectionAnalysis();
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
  templateCell.textContent = record.order_type === "corrected"
    ? `${templateLabel(record.template)} · Corrected`
    : templateLabel(record.template);
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
    const rowDetail = hasCount && Number.isFinite(count) ? `${count} order ${count === 1 ? "row" : "rows"}` : "Workbook created";
    const applied = Number(record.applied_change_count);
    const warnings = Number(record.warning_count);
    const correctionDetail = record.order_type === "corrected"
      ? ` · ${Number.isFinite(applied) ? applied : 0} changes · ${Number.isFinite(warnings) ? warnings : 0} warnings`
      : "";
    detailsCell.textContent = `${rowDetail}${correctionDetail}`;
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
  if (isBusy) buttonLabel.textContent = correctionAnalysis ? "Creating corrected workbook…" : selectedOrderType() === "corrected" ? "Analyzing corrections…" : "Creating workbook…";
  else if (selectedOrderType() === "corrected") buttonLabel.textContent = correctionAnalysis ? "Generate corrected Excel" : "Analyze corrections";
  else buttonLabel.textContent = "Convert to Excel";
  templateInputs.forEach((input) => {
    const correctedSaussy = selectedOrderType() === "corrected" && input.value === "saussy";
    input.disabled = isBusy || correctedSaussy || input.dataset.comingSoon === "true";
  });
  orderTypeInputs.forEach((input) => { input.disabled = isBusy; });
  fileInput.disabled = isBusy;
  originalFileInput.disabled = isBusy;
  correctedFileInput.disabled = isBusy;
  reviewList.querySelectorAll("input").forEach((input) => { input.disabled = isBusy; });
  removeFileButton.disabled = isBusy;
  removeOriginalFileButton.disabled = isBusy;
  removeCorrectedFileButton.disabled = isBusy;
  convertButton.classList.toggle("is-loading", isBusy);
}

function outputFilename(pdfName) {
  return `${pdfName.slice(0, -4)}.xlsx`;
}

function correctedOutputFilename(pdfName) {
  return `${pdfName.slice(0, -4)}-Corrected.xlsx`;
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

function showCorrectedFileError(kind, message) {
  const isOriginal = kind === "original";
  const error = isOriginal ? originalFileError : correctedFileError;
  const zone = isOriginal ? originalDropZone : correctedDropZone;
  error.textContent = message;
  error.hidden = false;
  zone.classList.add("has-error");
}

function selectCorrectedFile(kind, file) {
  const isOriginal = kind === "original";
  const error = isOriginal ? originalFileError : correctedFileError;
  const zone = isOriginal ? originalDropZone : correctedDropZone;
  error.hidden = true;
  error.textContent = "";
  zone.classList.remove("has-error");
  clearDownload();
  hideStatus();
  resetCorrectionAnalysis();
  if (!file) return;
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return showCorrectedFileError(kind, `Choose a PDF file for the ${kind} order.`);
  if (file.size > MAX_FILE_SIZE) return showCorrectedFileError(kind, `The ${kind} PDF is larger than 4 MB.`);
  if (isOriginal) {
    selectedOriginalFile = file;
    originalFileName.textContent = file.name;
    originalFileSize.textContent = `${formatFileSize(file.size)} · Original order`;
    originalDropZone.hidden = true;
    originalFileCard.hidden = false;
  } else {
    selectedCorrectedFile = file;
    correctedFileName.textContent = file.name;
    correctedFileSize.textContent = `${formatFileSize(file.size)} · Corrected order`;
    correctedDropZone.hidden = true;
    correctedFileCard.hidden = false;
  }
  if (selectedOriginalFile && selectedCorrectedFile) {
    if (selectedOriginalFile.size + selectedCorrectedFile.size > MAX_FILE_SIZE) {
      showCorrectedFileError("corrected", "Together, the two PDFs must be 4 MB or smaller.");
    }
    if (
      selectedOriginalFile.name === selectedCorrectedFile.name
      && selectedOriginalFile.size === selectedCorrectedFile.size
      && selectedOriginalFile.lastModified === selectedCorrectedFile.lastModified
    ) {
      showCorrectedFileError("corrected", "Choose two different PDFs. The selected files appear identical.");
    }
  }
  updateConvertButtonState();
}

function updateOrderType() {
  const isCorrected = selectedOrderType() === "corrected";
  newOrderSection.hidden = isCorrected;
  correctedOrderSection.hidden = !isCorrected;
  correctionTemplateNote.hidden = !isCorrected;
  const saussy = templateInputs.find((input) => input.value === "saussy");
  if (saussy) {
    saussy.disabled = isCorrected || conversionIsBusy;
    if (isCorrected && saussy.checked) saussy.checked = false;
  }
  clearTemplateError();
  clearDownload();
  hideStatus();
  resetCorrectionAnalysis();
  updateConvertButtonState();
}

function wireDropZone(zone, select) {
  ["dragenter", "dragover"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.add("is-dragging");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      zone.classList.remove("is-dragging");
    });
  });
  zone.addEventListener("drop", (event) => select(event.dataTransfer.files[0]));
}

fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));
removeFileButton.addEventListener("click", clearFile);
originalFileInput.addEventListener("change", () => selectCorrectedFile("original", originalFileInput.files[0]));
correctedFileInput.addEventListener("change", () => selectCorrectedFile("corrected", correctedFileInput.files[0]));
removeOriginalFileButton.addEventListener("click", () => clearCorrectedFile("original"));
removeCorrectedFileButton.addEventListener("click", () => clearCorrectedFile("corrected"));
orderTypeInputs.forEach((input) => input.addEventListener("change", updateOrderType));
templateInputs.forEach((input) => {
  input.addEventListener("change", () => {
    clearTemplateError();
    resetCorrectionAnalysis();
    updateConvertButtonState();
  });
});
historyRetry.addEventListener("click", () => loadHistory({ reset: true }));
historyLoadMore.addEventListener("click", () => loadHistory());

wireDropZone(dropZone, selectFile);
wireDropZone(originalDropZone, (file) => selectCorrectedFile("original", file));
wireDropZone(correctedDropZone, (file) => selectCorrectedFile("corrected", file));

function scrollStatusIntoView() {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  statusMessage.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
}

function validateTemplate() {
  const template = selectedTemplate();
  if (template) return template;
  templateError.textContent = selectedOrderType() === "corrected"
    ? "Choose the Classica template for corrected orders."
    : "Choose either the Saussy or Classica template.";
  templateError.hidden = false;
  const firstEnabled = templateInputs.find((input) => !input.disabled);
  firstEnabled?.focus();
  updateConvertButtonState();
  return "";
}

function addSuccessfulHistoryRecord(record) {
  addHistoryRecords([record], { prepend: true });
  historyTotal += 1;
  historyOffset += 1;
  updateHistoryState();
}

function exposeDownload(workbook, filename) {
  clearDownload();
  currentDownloadUrl = URL.createObjectURL(workbook);
  downloadLink.href = currentDownloadUrl;
  downloadLink.download = filename;
  downloadLink.hidden = false;
}

function renderCorrectionReview(analysis) {
  reviewList.replaceChildren();
  const reviewActions = analysis.actions.filter((action) => action.confidence === "review");
  reviewActions.forEach((action, index) => {
    const card = document.createElement("article");
    card.className = "review-card";
    const header = document.createElement("div");
    header.className = "review-card-header";
    const title = document.createElement("h3");
    title.textContent = `${action.room || "Unmatched room"} · ${action.item_type || "Order instruction"}`;
    const badge = document.createElement("span");
    badge.className = "review-action-badge";
    badge.textContent = action.operation;
    header.append(title, badge);

    const values = document.createElement("div");
    values.className = "review-values";
    [["Original", action.before_value || "No matched value"], ["Proposed", action.after_value || "No replacement value"]]
      .forEach(([label, value], valueIndex) => {
        const block = document.createElement("div");
        block.className = `review-value${valueIndex === 1 ? " is-after" : ""}`;
        const strong = document.createElement("strong");
        strong.textContent = label;
        const span = document.createElement("span");
        span.textContent = value;
        block.append(strong, span);
        values.append(block);
      });

    const evidence = document.createElement("p");
    evidence.className = "review-evidence";
    evidence.textContent = `Corrected-order evidence: ${action.evidence_corrected || "No exact excerpt was available."}`;
    card.append(header, values, evidence);
    if (action.warnings?.length) {
      const warning = document.createElement("p");
      warning.className = "review-warning";
      warning.textContent = action.warnings.join(" ");
      card.append(warning);
    }

    const decisions = document.createElement("div");
    decisions.className = "review-decisions";
    decisions.setAttribute("role", "radiogroup");
    decisions.setAttribute("aria-label", `Decision for ${title.textContent}`);
    [["apply", "Apply proposed change"], ["ignore", "Ignore this change"]].forEach(([value, label]) => {
      const option = document.createElement("label");
      option.className = "review-decision";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `correction-decision-${action.id}`;
      input.value = value;
      input.addEventListener("change", () => {
        correctionDecisions[action.id] = value;
        reviewError.hidden = true;
        updateConvertButtonState();
      });
      option.append(input, document.createTextNode(label));
      decisions.append(option);
    });
    card.append(decisions);
    reviewList.append(card);
    if (index === 0) card.dataset.firstReview = "true";
  });
  correctionReview.hidden = false;
  buttonLabel.textContent = "Generate corrected Excel";
  updateConvertButtonState();
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  correctionReview.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  reviewList.querySelector("input")?.focus();
}

async function convertNewOrder(template) {
  const attemptedFile = selectedFile;
  const data = new FormData();
  data.append("pdf", attemptedFile, attemptedFile.name);
  data.append("template", template);
  const response = await fetch("/api/convert", { method: "POST", body: data });
  if (!response.ok) {
    const failure = await readErrorResponse(response);
    if (failure.body?.conversion) addSuccessfulHistoryRecord(failure.body.conversion);
    const archiveNote = failure.body?.history_saved === false ? " This failure was not added to shared history." : "";
    throw new Error(`${failure.message}${archiveNote}`);
  }
  const workbook = await response.blob();
  const filename = outputFilename(attemptedFile.name);
  exposeDownload(workbook, filename);
  const historySaved = response.headers.get("X-History-Saved") === "true";
  if (historySaved) {
    addSuccessfulHistoryRecord({
      id: response.headers.get("X-Conversion-Id"),
      source_filename: attemptedFile.name,
      output_filename: filename,
      template,
      order_type: "new",
      status: "success",
      failure_reason: "",
      row_count: Number(response.headers.get("X-Order-Row-Count")),
      created_at_utc: response.headers.get("X-Conversion-Created-At"),
    });
  }
  const detail = historySaved ? filename : `${filename} — ready to download, but it was not added to shared history.`;
  showStatus("success", "Your workbook is ready", detail);
  resetFilePicker();
  resetTemplateSelection();
  downloadLink.focus();
}

async function analyzeCorrectedOrder(template) {
  const data = new FormData();
  data.append("original_pdf", selectedOriginalFile, selectedOriginalFile.name);
  data.append("corrected_pdf", selectedCorrectedFile, selectedCorrectedFile.name);
  data.append("template", template);
  const response = await fetch("/api/corrections/analyze", { method: "POST", body: data });
  if (!response.ok) {
    const failure = await readErrorResponse(response);
    throw new Error(failure.message);
  }
  correctionAnalysis = await response.json();
  correctionDecisions = {};
  const reviewCount = correctionAnalysis.actions.filter((action) => action.confidence === "review").length;
  if (reviewCount) {
    renderCorrectionReview(correctionAnalysis);
    showStatus("success", "Analysis complete", `${reviewCount} uncertain ${reviewCount === 1 ? "change needs" : "changes need"} your decision.`);
    return false;
  }
  return true;
}

async function generateCorrectedOrder(template) {
  const attemptedOriginal = selectedOriginalFile;
  const attemptedCorrected = selectedCorrectedFile;
  const data = new FormData();
  data.append("original_pdf", attemptedOriginal, attemptedOriginal.name);
  data.append("corrected_pdf", attemptedCorrected, attemptedCorrected.name);
  data.append("template", template);
  data.append("analysis", JSON.stringify(correctionAnalysis));
  data.append("decisions", JSON.stringify(correctionDecisions));
  const response = await fetch("/api/corrections/generate", { method: "POST", body: data });
  if (!response.ok) {
    const failure = await readErrorResponse(response);
    throw new Error(failure.message);
  }
  const workbook = await response.blob();
  const filename = correctedOutputFilename(attemptedCorrected.name);
  exposeDownload(workbook, filename);
  const historySaved = response.headers.get("X-History-Saved") === "true";
  if (historySaved) {
    addSuccessfulHistoryRecord({
      id: response.headers.get("X-Conversion-Id"),
      source_filename: attemptedCorrected.name,
      output_filename: filename,
      template,
      order_type: "corrected",
      original_filename: attemptedOriginal.name,
      corrected_filename: attemptedCorrected.name,
      status: "success",
      failure_reason: "",
      row_count: Number(response.headers.get("X-Order-Row-Count")),
      applied_change_count: Number(response.headers.get("X-Applied-Change-Count")),
      warning_count: Number(response.headers.get("X-Warning-Count")),
      created_at_utc: response.headers.get("X-Conversion-Created-At"),
    });
  }
  const warnings = Number(response.headers.get("X-Warning-Count")) || 0;
  const detail = `${filename}${warnings ? ` · ${warnings} ${warnings === 1 ? "warning" : "warnings"} in Revision Report` : ""}${historySaved ? "" : " · not added to shared history"}`;
  showStatus("success", "Your corrected workbook is ready", detail);
  resetCorrectedFiles();
  resetTemplateSelection();
  downloadLink.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const isCorrected = selectedOrderType() === "corrected";
  if (!isCorrected && !selectedFile) {
    showError("Upload a PDF before starting the conversion.");
    fileInput.focus();
    return;
  }
  if (isCorrected && (!selectedOriginalFile || !selectedCorrectedFile)) {
    if (!selectedOriginalFile) showCorrectedFileError("original", "Upload the original order PDF.");
    if (!selectedCorrectedFile) showCorrectedFileError("corrected", "Upload the corrected order PDF.");
    (selectedOriginalFile ? correctedFileInput : originalFileInput).focus();
    return;
  }
  if (isCorrected && selectedOriginalFile.size + selectedCorrectedFile.size > MAX_FILE_SIZE) {
    showCorrectedFileError("corrected", "Together, the two PDFs must be 4 MB or smaller.");
    correctedFileInput.focus();
    return;
  }
  const template = validateTemplate();
  if (!template) return;
  if (isCorrected && template !== "classica") {
    templateError.textContent = "Corrected orders currently support Classica only.";
    templateError.hidden = false;
    return;
  }
  if (isCorrected && correctionAnalysis) {
    const unresolved = correctionAnalysis.actions
      .filter((action) => action.confidence === "review")
      .some((action) => !correctionDecisions[action.id]);
    if (unresolved) {
      reviewError.textContent = "Choose Apply or Ignore for every uncertain change.";
      reviewError.hidden = false;
      reviewList.querySelector("input:not(:checked)")?.focus();
      return;
    }
  }

  clearDownload();
  setBusy(true);
  showStatus(
    "processing",
    isCorrected && !correctionAnalysis ? "Analyzing both orders" : isCorrected ? "Creating your corrected workbook" : "Creating your workbook",
    isCorrected ? "Comparing revisions and preserving the original generated quantities where needed." : "Reading the PDF and preparing the Excel file. This may take a moment.",
  );
  scrollStatusIntoView();
  try {
    if (!isCorrected) {
      await convertNewOrder(template);
    } else {
      const readyToGenerate = correctionAnalysis || await analyzeCorrectedOrder(template);
      if (readyToGenerate) await generateCorrectedOrder(template);
    }
  } catch (error) {
    const message = error instanceof TypeError
      ? "The converter could not be reached. Check your connection and try again."
      : error instanceof Error
        ? error.message
        : "The conversion failed. Please try again.";
    showStatus("error", isCorrected ? "Could not process the corrected order" : "Could not create the workbook", message);
  } finally {
    setBusy(false);
  }
});

window.addEventListener("beforeunload", () => {
  if (currentDownloadUrl) URL.revokeObjectURL(currentDownloadUrl);
});

updateOrderType();
loadHistory({ reset: true });
