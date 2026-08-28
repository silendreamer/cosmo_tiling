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

const MAX_FILE_SIZE = 4 * 1024 * 1024;
let selectedFile = null;
let downloadUrl = null;

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
  if (downloadUrl) {
    URL.revokeObjectURL(downloadUrl);
    downloadUrl = null;
  }
  downloadLink.hidden = true;
  downloadLink.removeAttribute("download");
  downloadLink.href = "#";
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
  } catch (_error) {
    // The fallback below covers non-JSON platform errors.
  }
  if (response.status === 413) {
    return "This file is too large for the web converter. Choose a PDF under 4 MB.";
  }
  return "The workbook could not be created. Check the PDF and template, then try again.";
}

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  fileCard.hidden = true;
  dropZone.hidden = false;
  convertButton.disabled = true;
  clearDownload();
  hideStatus();
  clearError();
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
  statusMessage.scrollIntoView({ behavior: "smooth", block: "nearest" });

  const data = new FormData();
  data.append("pdf", selectedFile, selectedFile.name);
  data.append("template", form.elements.template.value);

  try {
    const response = await fetch("/api/convert", {
      method: "POST",
      body: data,
    });
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }

    const workbook = await response.blob();
    const filename = outputFilename(selectedFile.name);
    downloadUrl = URL.createObjectURL(workbook);
    downloadLink.href = downloadUrl;
    downloadLink.download = filename;
    downloadLink.hidden = false;
    showStatus(
      "success",
      "Your workbook is ready",
      filename,
    );
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

window.addEventListener("beforeunload", clearDownload);
