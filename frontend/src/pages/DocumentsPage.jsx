import { useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { AlertTriangle, Layers, Download } from "lucide-react";
import { toast } from "sonner";
import { useDocumentsList } from "../hooks/useDocumentsQueries";
import { documentsApi } from "../api/documents";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";
import { cn } from "../lib/utils";

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
  const [invoiceNo, setInvoiceNo] = useState(searchParams.get("invoiceNo") || "");
  const [consigneeCode, setConsigneeCode] = useState(searchParams.get("consigneeCode") || "");
  const [date, setDate] = useState(searchParams.get("date") || "");

  const page = Number(searchParams.get("page") || 1);
  const range = searchParams.get("range") || "";
  const listParams = {
    page,
    limit: PAGE_SIZE,
    invoiceNo: searchParams.get("invoiceNo") || undefined,
    consigneeCode: searchParams.get("consigneeCode") || undefined,
    date: searchParams.get("date") || undefined,
    range: range || undefined,
  };
  const query = useDocumentsList(listParams);
  const [downloadingAll, setDownloadingAll] = useState(false);

  const handleDownloadAll = async () => {
    setDownloadingAll(true);
    try {
      const { blob, included, skipped } = await documentsApi.downloadAll(listParams);
      if (included === 0) {
        toast.error("Nothing to download - every document's files on this page are gone.");
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
      toast.error(error.userMessage || "Could not download documents.");
    } finally {
      setDownloadingAll(false);
    }
  };

  const runSearch = (e) => {
    e.preventDefault();
    const params = {};
    if (invoiceNo) params.invoiceNo = invoiceNo;
    if (consigneeCode) params.consigneeCode = consigneeCode;
    if (date) params.date = date;
    if (range) params.range = range;
    params.page = "1";
    setSearchParams(params);
  };

  const goToPage = (p) => {
    setSearchParams({ ...Object.fromEntries(searchParams), page: String(p) });
  };

  const selectRange = (value) => {
    const params = Object.fromEntries(searchParams);
    if (value) {
      params.range = value;
    } else {
      delete params.range;
    }
    params.page = "1";
    setSearchParams(params);
  };

  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Documents</h1>
        <div className="flex items-center gap-2">
          <Link
            to="/documents/view-all"
            className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
          >
            View All Details
          </Link>
          <button
            type="button"
            onClick={handleDownloadAll}
            disabled={downloadingAll || !query.data?.items.length}
            className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50 disabled:opacity-30"
          >
            <Download size={14} />
            {downloadingAll ? "Zipping..." : "Download All"}
          </button>
        </div>
      </div>

      <form onSubmit={runSearch} className="flex flex-wrap gap-2 mb-6 bg-surface border border-border rounded-lg p-3">
        <input
          placeholder="Invoice No"
          value={invoiceNo}
          onChange={(e) => setInvoiceNo(e.target.value)}
          className="rounded border border-border bg-bg px-3 py-1.5 text-sm flex-1 min-w-[140px]"
        />
        <input
          placeholder="Consignee Code"
          value={consigneeCode}
          onChange={(e) => setConsigneeCode(e.target.value)}
          className="rounded border border-border bg-bg px-3 py-1.5 text-sm flex-1 min-w-[140px]"
        />
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="rounded border border-border bg-bg px-3 py-1.5 text-sm"
        />
        <button type="submit" className="bg-accent text-bg rounded px-4 py-1.5 text-sm font-medium hover:bg-accent-dim">
          Search
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-2 mb-6">
        <span className="text-xs text-text-muted">Uploaded:</span>
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.value || "all"}
            type="button"
            onClick={() => selectRange(opt.value)}
            className={cn(
              "px-3 py-1 rounded-full border text-xs font-medium",
              range === opt.value
                ? "bg-accent text-bg border-accent"
                : "border-border text-text-muted hover:border-accent/50"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {query.isLoading ? (
        <LoadingState message="Loading documents..." />
      ) : query.data?.items.length === 0 ? (
        <p className="text-sm text-text-muted py-10 text-center">No documents found.</p>
      ) : (
        <div className="space-y-2">
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
                  {doc.hasLowConfidenceFields && (
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
