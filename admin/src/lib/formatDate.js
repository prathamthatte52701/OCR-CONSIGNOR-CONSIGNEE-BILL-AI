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

// Calendar day in IST as YYYY-MM-DD (groups chat messages under date separators).
export function dayKeyIST(dateStr) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST_ZONE }).format(new Date(dateStr));
}
