const ACCEPTED_TYPES = ["image/jpeg", "image/jpg", "image/png", "application/pdf"];
const MAX_SIZE_MB = 5;

// Same type/size rules the backend enforces (copied from the ACKN project).
export function validateDocumentFile(file) {
  if (file.size === 0) return "This file is empty.";
  if (!ACCEPTED_TYPES.includes(file.type)) return "Only JPG, JPEG, PNG, and PDF files are allowed.";
  if (file.size > MAX_SIZE_MB * 1024 * 1024) return `File size must be ${MAX_SIZE_MB} MB or less.`;
  return null;
}

export function formatSize(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
