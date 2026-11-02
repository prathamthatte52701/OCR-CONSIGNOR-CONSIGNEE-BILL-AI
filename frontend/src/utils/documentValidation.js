const ACCEPTED_TYPES = ["image/jpeg", "image/jpg", "image/png", "application/pdf"];
const MAX_SIZE_MB = 5;

const EXTENSION_TYPES = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", pdf: "application/pdf" };

// Some OS/browser setups report an empty or generic type for a valid file: fall back to the
// extension (the backend still sniffs the real bytes).
function effectiveType(file) {
  if (file.type && file.type !== "application/octet-stream") return file.type;
  return EXTENSION_TYPES[file.name?.split(".").pop()?.toLowerCase()] ?? file.type;
}

// Same type/size rules the backend enforces (copied from the ACKN project).
export function validateDocumentFile(file) {
  if (file.size === 0) return "This file is empty.";
  if (!ACCEPTED_TYPES.includes(effectiveType(file))) return "Only JPG, JPEG, PNG, and PDF files are allowed.";
  if (file.size > MAX_SIZE_MB * 1024 * 1024) return `File size must be ${MAX_SIZE_MB} MB or less.`;
  return null;
}

export function formatSize(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
