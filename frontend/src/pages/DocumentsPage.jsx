import { useEffect, useRef, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { AlertTriangle, Layers, Download } from "lucide-react";
import { toast } from "sonner";
import { useDocumentsList } from "../hooks/useDocumentsQueries";
import { documentsApi } from "../api/documents";
import { readErrorMessage } from "../api/client";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";
import { cn } from "../lib/utils";
import { needsAttention } from "../lib/needsAttention";
import {
  MONTH_NAMES,
  apiParamsFromFilters,
  describeFilters,
  filtersFromSearchParams,
  hasActiveFilters,
  parsePage,
  urlParamsFromFilters,
} from "../lib/documentFilters";

const PAGE_SIZE = 30;

// Feature 7: card border reflects the worst (minimum) field confidence across the whole
// document. `minConfidence` is absent on documents processed before this field existed -
// that's the neutral/fallback case, not an error, so it falls through to the plain border.
function confidenceBorderClass(minConfidence) {
  if (typeof minConfidence !== "number") return "border border-border";
  if (minConfidence >= 90) return "border-2 border-accent";
  if (minConfidence >= 70) return "border-2 border-warning";
  return "border-2 border-danger";
}

const RANGE_OPTIONS = [
  { value: "", label: "All time" },
  { value: "today", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "year", label: "This Year" },
];

const STATUS_STYLES = {
  processed: "bg-accent/15 text-accent",
  processing: "bg-warning/15 text-warning",
  uploaded: "bg-warning/15 text-warning",
  failed: "bg-danger/15 text-danger",
};

export default function DocumentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = filtersFromSearchParams(searchParams);
  const page = parsePage(searchParams);
  const [searchText, setSearchText] = useState(filters.search);
  const [pickedYear, setPickedYear] = useState(
    /^\d{4}-/.test(filters.month) ? filters.month.slice(0, 4) : String(new Date().getFullYear())
  );
  const query = useDocumentsList({ ...apiParamsFromFilters(filters), page, limit: PAGE_SIZE });
  const [downloadingAll, setDownloadingAll] = useState(false);
  const downloadingRef = useRef(false);

  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // A page past the end (a deleted last page, a hand-edited URL) goes to the last real page.
  useEffect(() => {
    if (query.data && !query.isPlaceholderData && page > totalPages) {
      setSearchParams(
        { ...Object.fromEntries(searchParams), page: String(totalPages) },
        { replace: true }
      );
    }
  }, [query.data, query.isPlaceholderData, page, totalPages, searchParams, setSearchParams]);

  // Keep the search box in step when the URL changes from outside (Clear, back button).
  useEffect(() => setSearchText(filters.search), [filters.search]);

  // Any filter change goes back to page 1.
  const applyFilters = (next) => {
    setSearchParams({ ...urlParamsFromFilters(next), page: "1" });
  };

  const runSearch = (e) => {
    e.preventDefault();
    applyFilters({ ...filters, search: searchText.trim() });
  };

  // The date picker and the month filter clear each other.
  const pickDate = (value) =>
    applyFilters({ ...filters, date: value, month: value ? "" : filters.month });
  const pickMonth = (value) =>
    applyFilters({ ...filters, month: value, date: value ? "" : filters.date });
  const selectedMonthNumber = /^\d{4}-\d{2}$/.test(filters.month) ? filters.month.slice(5) : "";
  const onMonthSelect = (mm) => pickMonth(mm ? `${pickedYear}-${mm}` : "");
  const onYearSelect = (year) => {
    setPickedYear(year);
    if (selectedMonthNumber) pickMonth(`${year}-${selectedMonthNumber}`);
  };
  const thisYear = new Date().getFullYear();
  // thisYear-9 .. thisYear+1, plus the year from the URL when it is outside that range.
  const years = Array.from({ length: 11 }, (_, i) => String(thisYear - 9 + i));
  if (!years.includes(pickedYear)) years.push(pickedYear);
  years.sort();

  const goToPage = (p) => {
    setSearchParams({ ...Object.fromEntries(searchParams), page: String(p) });
  };

  const filterDescription = describeFilters(filters);
  const viewAllLink = `/documents/view-all${
    hasActiveFilters(filters) ? `?${new URLSearchParams(urlParamsFromFilters(filters))}` : ""
  }`;

  const handleDownloadAll = async () => {
    if (downloadingRef.current) return; // state alone lags a fast double click
    const ids = (query.data?.items || []).map((d) => d.id);
    if (!ids.length) return;
    downloadingRef.current = true;
    setDownloadingAll(true);
    try {
      const { blob, included, skipped } = await documentsApi.downloadAll(ids);
      if (included === 0) {
        toast.error("Nothing to download - the files of these documents are gone.");
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "documents.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(
        `Downloaded ${included} of ${included + skipped} document${included + skipped === 1 ? "" : "s"}${
          skipped ? ` (${skipped} skipped)` : ""
        }.`
      );
    } catch (error) {
      toast.error(await readErrorMessage(error, "Could not download documents."));
    } finally {
      downloadingRef.current = false;
      setDownloadingAll(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Documents</h1>
        <div className="flex items-center gap-2">
          <Link
            to={viewAllLink}
            className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
          >
            View All Details
          </Link>
          <button
            type="button"
            onClick={handleDownloadAll}
            disabled={downloadingAll || query.isPlaceholderData || !query.data?.items.length}
            className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50 disabled:opacity-30"
          >
            <Download size={14} />
            {downloadingAll ? "Zipping..." : "Download All"}
          </button>
        </div>
      </div>

      <form
        onSubmit={runSearch}
        className="flex flex-wrap items-center gap-2 mb-3 bg-surface border border-border rounded-lg p-3"
      >
        <input
          placeholder="Invoice no, consignee code or name"
          value={searchText}
          maxLength={100}
          onChange={(e) => setSearchText(e.target.value)}
          className="rounded border border-border bg-bg px-3 py-1.5 text-sm flex-1 min-w-[220px]"
        />
        <button
          type="submit"
          className="bg-accent text-bg rounded px-4 py-1.5 text-sm font-medium hover:bg-accent-dim"
        >
          Search
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-xs text-text-muted">Document date:</span>
        <input
          type="date"
          value={filters.date}
          onChange={(e) => pickDate(e.target.value)}
          aria-label="Document date"
          className="rounded border border-border bg-bg px-2 py-1 text-xs"
        />
        <select
          value={selectedMonthNumber}
          onChange={(e) => onMonthSelect(e.target.value)}
          aria-label="Month"
          className="rounded border border-border bg-bg px-2 py-1 text-xs"
        >
          <option value="">All months</option>
          {MONTH_NAMES.map((name, i) => (
            <option key={name} value={String(i + 1).padStart(2, "0")}>
              {name}
            </option>
          ))}
        </select>
        <select
          value={pickedYear}
          onChange={(e) => onYearSelect(e.target.value)}
          aria-label="Year"
          className="rounded border border-border bg-bg px-2 py-1 text-xs"
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => pickMonth(filters.month === "none" ? "" : "none")}
          className={cn(
            "px-3 py-1 rounded-full border text-xs font-medium",
            filters.month === "none"
              ? "bg-accent text-bg border-accent"
              : "border-border text-text-muted hover:border-accent/50"
          )}
        >
          No date found
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-xs text-text-muted">Uploaded:</span>
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.value || "all"}
            type="button"
            onClick={() => applyFilters({ ...filters, range: opt.value })}
            className={cn(
              "px-3 py-1 rounded-full border text-xs font-medium",
              filters.range === opt.value
                ? "bg-accent text-bg border-accent"
                : "border-border text-text-muted hover:border-accent/50"
            )}
          >
            {opt.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => applyFilters({ ...filters, needsReview: !filters.needsReview })}
          className={cn(
            "px-3 py-1 rounded-full border text-xs font-medium",
            filters.needsReview
              ? "bg-warning text-bg border-warning"
              : "border-border text-text-muted hover:border-warning/50"
          )}
        >
          Needs review
        </button>
        {["failed", "processed"].map((status) => (
          <button
            key={status}
            type="button"
            onClick={() =>
              applyFilters({ ...filters, status: filters.status === status ? "" : status })
            }
            className={cn(
              "px-3 py-1 rounded-full border text-xs font-medium capitalize",
              filters.status === status
                ? "bg-accent text-bg border-accent"
                : "border-border text-text-muted hover:border-accent/50"
            )}
          >
            {status}
          </button>
        ))}
      </div>

      {filterDescription.length > 0 && (
        <p className="flex flex-wrap items-center gap-2 mb-4 text-xs text-text-muted">
          <span>Filtered by {filterDescription.join(", ")}</span>
          <button
            type="button"
            onClick={() => setSearchParams({ page: "1" })}
            className="rounded border border-border px-2 py-0.5 hover:border-accent/50"
          >
            Clear
          </button>
        </p>
      )}

      {query.isPlaceholderData && (
        <p className="mb-2 text-xs text-text-muted" role="status">
          Updating...
        </p>
      )}

      {query.isLoading ? (
        <LoadingState message="Loading documents..." />
      ) : query.isError ? (
        <div className="text-center py-10">
          <p className="text-sm text-danger mb-3">
            {query.error?.userMessage || "Could not load your documents. Please try again."}
          </p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
          >
            Retry
          </button>
        </div>
      ) : query.data.items.length === 0 ? (
        <p className="text-sm text-text-muted py-10 text-center">No documents found.</p>
      ) : (
        <div className={cn("space-y-2", query.isPlaceholderData && "opacity-50")}>
          {query.data.items.map((doc, index) => (
            <Link
              key={doc.id}
              to={`/documents/${doc.id}`}
              className={cn(
                "flex items-center justify-between gap-3 bg-surface rounded-lg px-4 py-3 hover:border-accent/50",
                confidenceBorderClass(doc.minConfidence)
              )}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted shrink-0">
                    #{(page - 1) * PAGE_SIZE + index + 1}
                  </span>
                  <span className="font-medium text-sm truncate">
                    {doc.invoiceNo || "(no invoice no.)"}
                  </span>
                  {needsAttention(doc) && (
                    <AlertTriangle size={14} className="text-warning shrink-0" />
                  )}
                  {doc.multiPage && <Layers size={14} className="text-text-muted shrink-0" />}
                </div>
                <p className="text-xs text-text-muted truncate">
                  {doc.consignee || "-"} &middot; {doc.consigneeCode || "-"} &middot;{" "}
                  {formatIST(doc.createdAt)}
                </p>
              </div>
              <span
                className={cn(
                  "text-xs px-2 py-0.5 rounded-full shrink-0",
                  STATUS_STYLES[doc.uploadStatus] || "bg-surface-raised text-text-muted"
                )}
              >
                {doc.uploadStatus}
              </span>
            </Link>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-6 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => goToPage(page - 1)}
            className="px-3 py-1.5 rounded border border-border disabled:opacity-30"
          >
            Previous
          </button>
          <span className="text-text-muted">
            Page {page} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => goToPage(page + 1)}
            className="px-3 py-1.5 rounded border border-border disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
