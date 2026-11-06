const ACCOUNT_CODES = ["ACCOUNT_PENDING", "ACCOUNT_REJECTED", "ACCOUNT_REVOKED"];
const IST_ZONE = "Asia/Kolkata";

function formatDate(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: IST_ZONE,
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Plain text for a 403 login detail object; null when it is not an account-status detail.
export function accountStatusText(d) {
  if (!d || typeof d !== "object" || !ACCOUNT_CODES.includes(d.code)) return null;
  const reason = d.reason || "No reason was given";
  const on = d.decidedAt ? ` on ${formatDate(d.decidedAt)}` : "";
  if (d.code === "ACCOUNT_PENDING") {
    const sent = d.requestedAt ? `Your request was sent on ${formatDate(d.requestedAt)}. ` : "";
    return `${sent}The admin has not decided yet. Log in again later to check. No email is sent.`;
  }
  if (d.code === "ACCOUNT_REJECTED") {
    return `Your request was not approved${on}. Reason: ${reason}. Contact your admin.`;
  }
  return `Your access was removed${on}. Reason: ${reason}. Contact your admin.`;
}
