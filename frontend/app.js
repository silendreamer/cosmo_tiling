const form = document.querySelector("#converter-form");
const fileInput = document.querySelector("#pdf-file");
const dropZone = document.querySelector("#drop-zone");
const fileCard = document.querySelector("#file-card");
const fileName = document.querySelector("#file-name");
const fileSize = document.querySelector("#file-size");
const fileError = document.querySelector("#file-error");
const removeFileButton = document.querySelector("#remove-file");
const convertButton = document.querySelector("#convert-button");
const statusMessage = document.querySelector("#status-message");

const MAX_FILE_SIZE = 25 * 1024 * 1024;
let selectedFile = null;

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

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  fileCard.hidden = true;
  dropZone.hidden = false;
  convertButton.disabled = true;
  statusMessage.hidden = true;
  clearError();
}

function selectFile(file) {
  clearError();
  statusMessage.hidden = true;

  if (!file) {
    return;
  }

  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) {
    showError("Choose a PDF file to continue.");
    return;
  }
  if (file.size > MAX_FILE_SIZE) {
    showError("This PDF is larger than 25 MB. Choose a smaller file.");
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

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!selectedFile) {
    showError("Upload a PDF before starting the conversion.");
    dropZone.focus();
    return;
  }

  statusMessage.hidden = false;
  statusMessage.scrollIntoView({ behavior: "smooth", block: "nearest" });
});
