// Storage stays UTC everywhere; only display converts to IST.
const IST_ZONE = "Asia/Kolkata";

export function formatIST(dateStr, opts = {}) {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: IST_ZONE,
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    ...opts,
  }).format(date);
}

export function formatISTDate(dateStr) {
  return formatIST(dateStr, { hour: undefined, minute: undefined });
}

export function isTodayIST(dateStr) {
  if (!dateStr) return false;
  const fmt = { timeZone: IST_ZONE, year: "numeric", month: "2-digit", day: "2-digit" };
  const a = new Intl.DateTimeFormat("en-CA", fmt).format(new Date(dateStr));
  const b = new Intl.DateTimeFormat("en-CA", fmt).format(new Date());
  return a === b;
}
