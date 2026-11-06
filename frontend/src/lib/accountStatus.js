import { formatIST } from "./formatDate";

export const ACCOUNT_CODES = ["ACCOUNT_PENDING", "ACCOUNT_REJECTED", "ACCOUNT_REVOKED"];

const NOTICE_TONE = {
  ACCOUNT_PENDING: "warn",
  ACCOUNT_REJECTED: "danger",
  ACCOUNT_REVOKED: "danger",
};

// Plain text only: the admin's reason is user-controlled data and is never rendered as HTML.
export function accountStatusText(d) {
  const reason = d.reason || "No reason was given";
  const on = (value) => (value ? ` on ${formatIST(value)}` : "");
  if (d.code === "ACCOUNT_PENDING") {
    const sent = d.requestedAt ? `Your request was sent on ${formatIST(d.requestedAt)}. ` : "";
    return `${sent}The admin has not decided yet. Log in again later to check. No email is sent.`;
  }
  if (d.code === "ACCOUNT_REJECTED") {
    return `Your request was not approved${on(d.decidedAt)}. Reason: ${reason}. Contact your admin.`;
  }
  if (d.code === "ACCOUNT_REVOKED") {
    return `Your access was removed${on(d.decidedAt)}. Reason: ${reason}. Contact your admin.`;
  }
  return d.message || "";
}

// { tone, text } for a 403 detail object, or null when it is not an account-status detail.
export function accountNotice(detail) {
  if (!detail || typeof detail !== "object" || !ACCOUNT_CODES.includes(detail.code)) return null;
  return { tone: NOTICE_TONE[detail.code], text: accountStatusText(detail) };
}

// The session was ended by a 403 on a normal route: keep the detail for the login page.
const STORAGE_KEY = "main-ocr-account-notice";
export function stashAccountDetail(detail) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(detail));
  } catch {
    /* storage unavailable - the login page shows no notice */
  }
}
// Read without removing (StrictMode runs initializers twice in dev); the login page clears it
// after mount with clearStashedAccountNotice().
export function peekStashedAccountNotice() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? accountNotice(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}
export function clearStashedAccountNotice() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable - nothing to clear */
  }
}
