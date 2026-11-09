// Pure dashboard helpers (no React, no browser globals at import time).

export const isNum = (v) => typeof v === "number" && Number.isFinite(v);

/** Thousands-separated number; "-" for anything that is not a finite number (never throws). */
export const fmt = (n) => (isNum(n) ? n.toLocaleString("en-US") : "-");
export const lastN = (arr, n) => (Array.isArray(arr) && arr.length ? arr.slice(-n) : undefined);

export const sum = (arr) => (Array.isArray(arr) ? arr.reduce((a, b) => a + (isNum(b) ? b : 0), 0) : 0);

// "▲ +3 vs previous 7 days" / "▼ -2 ..." / "No change ..."; null when either number is missing.
export function trendText(current, previous, suffix = "vs previous 7 days") {
  if (!isNum(current) || !isNum(previous)) return null;
  const diff = current - previous;
  if (diff === 0) return `No change ${suffix}`;
  return `${diff > 0 ? "▲ +" : "▼ "}${diff} ${suffix}`;
}

// Success percentage with one decimal, or null when nothing has finished yet.
export function successRate(processed, failed) {
  if (!isNum(processed) || !isNum(failed)) return null;
  const finished = processed + failed;
  return finished > 0 ? Math.round((processed / finished) * 1000) / 10 : null;
}

// A series is only drawable when it lines up with its day labels.
export function seriesOk(days, values) {
  return Array.isArray(days) && Array.isArray(values) && days.length > 1 && values.length === days.length;
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

const SENTENCES = {
  login: (n) => `${n} logged in`,
  signup: (n) => `${n} requested an account`,
  password_change: (n) => `${n} changed a password`,
  password_reset_requested: (n) => `${n} asked for a password reset`,
  user_approved: (n) => `${n} approved a user`,
  user_rejected: (n) => `${n} rejected a user`,
  user_updated: (n) => `${n} updated a user`,
  user_deleted: (n) => `${n} deleted a user`,
  document_uploaded: (n, i) => `${n} uploaded ${plural(i.count, "document", "documents")}`,
  document_corrected: (n, i) => `${n} corrected ${plural(i.count, "document", "documents")}`,
  document_reprocessed: (n, i) => `${n} reprocessed ${plural(i.count, "document", "documents")}`,
  document_deleted: (n, i) => `${n} deleted ${plural(i.count, "document", "documents")}`,
  document_file_purged: (n, i) => `${n} purged ${plural(i.count, "original file", "original files")}`,
  orphaned_file_dismissed: (n) => `${n} dismissed an orphaned file`,
  orphaned_file_retry_succeeded: (n) => `${n} recovered an orphaned file`,
};

// A feed item as a readable sentence. Unknown actions get a safe generic sentence: never raw JSON.
export function describeActivity(item) {
  const name = item.user?.username || "A removed user";
  const fn = SENTENCES[item.action];
  if (fn) return fn(name, item);
  return `${name}: ${String(item.action || "did something").replace(/_/g, " ").trim()}`;
}

export function activityCategory(action = "") {
  if (action === "login" || action === "signup" || action.startsWith("password_")) return "Account";
  if (action.startsWith("user_")) return "Admin action";
  if (action.startsWith("document_")) return "Documents";
  return "Other";
}

export function relativeTime(iso, now = Date.now()) {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "";
  const sec = Math.round((t - now) / 1000);
  const abs = Math.abs(sec);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(sec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(sec / 3600), "hour");
  return rtf.format(Math.round(sec / 86400), "day");
}
