const form = document.querySelector("#converter-form");
const fileInput = document.querySelector("#pdf-file");
const dropZone = document.querySelector("#drop-zone");
const fileCard = document.querySelector("#file-card");
const fileName = document.querySelector("#file-name");
const fileSize = document.querySelector("#file-size");
const fileError = document.querySelector("#file-error");
const removeFileButton = document.querySelector("#remove-file");
const convertButton = document.querySelector("#convert-button");
const buttonLabel = convertButton.querySelector(".button-label");
const statusMessage = document.querySelector("#status-message");
const statusTitle = document.querySelector("#status-title");
const statusDetail = document.querySelector("#status-detail");
const downloadLink = document.querySelector("#download-link");
const historyBody = document.querySelector("#history-body");
const historyCount = document.querySelector("#history-count");
const historyEmpty = document.querySelector("#history-empty");
const historyTableWrap = document.querySelector("#history-table-wrap");

const MAX_FILE_SIZE = 4 * 1024 * 1024;
let selectedFile = null;
let historyTotal = 0;
const downloadUrls = new Set();

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

function clearDownload() {
  downloadLink.hidden = true;
  downloadLink.removeAttribute("download");
  downloadLink.href = "#";
}

function resetFilePicker() {
  selectedFile = null;
  fileInput.value = "";
  fileCard.hidden = true;
  dropZone.hidden = false;
  convertButton.disabled = true;
  clearError();
}

function templateLabel(template) {
  return template === "classica" ? "Classica" : "Saussy";
}

function addHistoryRecord({ filename, template, status, reason = "", url = "" }) {
  historyTotal += 1;
  historyCount.textContent = `${historyTotal} ${historyTotal === 1 ? "file" : "files"}`;
  historyEmpty.hidden = true;
  historyTableWrap.hidden = false;

  const row = document.createElement("tr");
  const fileCell = document.createElement("td");
  const templateCell = document.createElement("td");
  const statusCell = document.createElement("td");

  if (status === "success") {
    const fileLink = document.createElement("a");
    fileLink.className = "history-file-link";
    fileLink.href = url;
    fileLink.download = filename;
    fileLink.textContent = filename;
    fileLink.setAttribute("aria-label", `Download ${filename}`);
    fileCell.append(fileLink);
  } else {
    const fileText = document.createElement("span");
    fileText.className = "history-file-name";
    fileText.textContent = filename;
    fileCell.append(fileText);
  }

  templateCell.textContent = templateLabel(template);

  const badge = document.createElement("span");
  badge.className = `status-badge is-${status}`;
  badge.textContent = status === "success" ? "Success" : "Failed";
  statusCell.append(badge);

  if (reason) {
    const reasonText = document.createElement("span");
    reasonText.className = "status-reason";
    reasonText.textContent = reason;
    statusCell.append(reasonText);
  }

  row.append(fileCell, templateCell, statusCell);
  historyBody.prepend(row);
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
  form.setAttribute("aria-busy", String(isBusy));
  convertButton.disabled = isBusy || !selectedFile;
  buttonLabel.textContent = isBusy ? "Creating workbook…" : "Convert to Excel";
  form.querySelectorAll('input[name="template"]').forEach((input) => {
    input.disabled = isBusy;
  });
  removeFileButton.disabled = isBusy;
  convertButton.classList.toggle("is-loading", isBusy);
}

function outputFilename(pdfName) {
  return `${pdfName.slice(0, -4)}.xlsx`;
}

async function errorMessage(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      const details = body.detail.map((item) => item.msg).filter(Boolean).join(" ");
      if (details) {
        return details;
      }
    }
  } catch (_error) {
    // The fallback below covers non-JSON platform errors.
  }
  if (response.status === 404) {
    return "The conversion service is not available in this deployment. Contact the administrator.";
  }
  if (response.status === 413) {
    return "This file is too large for the web converter. Choose a PDF under 4 MB.";
  }
  if (response.status === 504) {
    return "The conversion took too long. Try the file again or contact the administrator.";
  }
  if (response.status >= 500) {
    return "The conversion service encountered an error. Try again or contact the administrator.";
  }
  return "The workbook could not be created. Check the PDF and template, then try again.";
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

  if (!file) {
    return;
  }

  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) {
    showError("Choose a PDF file to continue.");
    return;
  }
  if (file.size > MAX_FILE_SIZE) {
    showError("This PDF is larger than 4 MB. Choose a smaller file.");
    return;
  }

  selectedFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = `${formatFileSize(file.size)} · PDF document`;
  dropZone.hidden = true;
  fileCard.hidden = false;
  convertButton.disabled = false;
}

fileInput.addEventListener("change", () => selectFile(fileInput.files[0]));
removeFileButton.addEventListener("click", clearFile);

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

dropZone.addEventListener("drop", (event) => {
  selectFile(event.dataTransfer.files[0]);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFile) {
    showError("Upload a PDF before starting the conversion.");
    dropZone.focus();
    return;
  }

  clearDownload();
  setBusy(true);
  showStatus(
    "processing",
    "Creating your workbook",
    "Reading the PDF and preparing the Excel file. This may take a moment.",
  );
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  statusMessage.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });

  const attemptedFile = selectedFile;
  const attemptedTemplate = form.elements.template.value;
  const data = new FormData();
  data.append("pdf", attemptedFile, attemptedFile.name);
  data.append("template", attemptedTemplate);

  try {
    const response = await fetch("/api/convert", {
      method: "POST",
      body: data,
    });
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }

    const workbook = await response.blob();
    const filename = outputFilename(attemptedFile.name);
    const downloadUrl = URL.createObjectURL(workbook);
    downloadUrls.add(downloadUrl);
    downloadLink.href = downloadUrl;
    downloadLink.download = filename;
    downloadLink.hidden = false;
    addHistoryRecord({
      filename,
      template: attemptedTemplate,
      status: "success",
      url: downloadUrl,
    });
    showStatus(
      "success",
      "Your workbook is ready",
      filename,
    );
    resetFilePicker();
    downloadLink.focus();
  } catch (error) {
    const message = error instanceof TypeError
      ? "The converter could not be reached. Check your connection and try again."
      : error instanceof Error
        ? error.message
        : "The conversion failed. Please try again.";
    addHistoryRecord({
      filename: attemptedFile.name,
      template: attemptedTemplate,
      status: "failed",
      reason: message,
    });
    showStatus("error", "Could not create the workbook", message);
  } finally {
    setBusy(false);
  }
});

window.addEventListener("beforeunload", () => {
  downloadUrls.forEach((url) => URL.revokeObjectURL(url));
});
