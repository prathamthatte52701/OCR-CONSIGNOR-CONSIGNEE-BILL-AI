// Shared by the Documents list and View All Details: the URL query string is the source of
// truth for the filters, so a link between the two pages just carries the same params.

export const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const RANGE_LABELS = { today: "today", week: "this week", month: "this month", year: "this year" };

// URL search params -> { search, date, month, range, needsReview }
export function filtersFromSearchParams(sp) {
  return {
    search: sp.get("search") || "",
    date: sp.get("date") || "",
    month: sp.get("month") || "",
    range: sp.get("range") || "",
    needsReview: sp.get("needsReview") === "1",
  };
}

// Filters -> the params the list API takes (only the ones that are set).
export function apiParamsFromFilters(f) {
  const params = {};
  if (f.search) params.search = f.search;
  if (f.date) params.date = f.date;
  if (f.month) params.month = f.month;
  if (f.range) params.range = f.range;
  if (f.needsReview) params.needsReview = true;
  return params;
}

// Filters -> URL params (needsReview is written as 1).
export function urlParamsFromFilters(f) {
  const params = apiParamsFromFilters(f);
  if (params.needsReview) params.needsReview = "1";
  return params;
}

export function hasActiveFilters(f) {
  return Object.keys(apiParamsFromFilters(f)).length > 0;
}

function describeMonth(month) {
  if (month === "none") return "no date found";
  const [year, mm] = month.split("-");
  return `${MONTH_NAMES[Number(mm) - 1] || mm} ${year}`;
}

export function describeFilters(f) {
  const parts = [];
  if (f.search) parts.push(`"${f.search}"`);
  if (f.date) parts.push(`date ${f.date}`);
  if (f.month) parts.push(describeMonth(f.month));
  if (f.range) parts.push(`uploaded ${RANGE_LABELS[f.range] || f.range}`);
  if (f.needsReview) parts.push("needs review");
  return parts;
}

export function parsePage(sp) {
  return Math.max(1, parseInt(sp.get("page") || "1", 10) || 1);
}
