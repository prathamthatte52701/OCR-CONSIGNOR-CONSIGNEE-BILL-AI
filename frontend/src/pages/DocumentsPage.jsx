import { useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { AlertTriangle, Layers } from "lucide-react";
import { useDocumentsList } from "../hooks/useDocumentsQueries";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";
import { cn } from "../lib/utils";

const PAGE_SIZE = 30;

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
  const query = useDocumentsList({
    page,
    limit: PAGE_SIZE,
    invoiceNo: searchParams.get("invoiceNo") || undefined,
    consigneeCode: searchParams.get("consigneeCode") || undefined,
    date: searchParams.get("date") || undefined,
  });

  const runSearch = (e) => {
    e.preventDefault();
    const params = {};
    if (invoiceNo) params.invoiceNo = invoiceNo;
    if (consigneeCode) params.consigneeCode = consigneeCode;
    if (date) params.date = date;
    params.page = "1";
    setSearchParams(params);
  };

  const goToPage = (p) => {
    setSearchParams({ ...Object.fromEntries(searchParams), page: String(p) });
  };

  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Documents</h1>

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

      {query.isLoading ? (
        <LoadingState message="Loading documents..." />
      ) : query.data?.items.length === 0 ? (
        <p className="text-sm text-text-muted py-10 text-center">No documents found.</p>
      ) : (
        <div className="space-y-2">
          {query.data.items.map((doc) => (
            <Link
              key={doc.id}
              to={`/documents/${doc.id}`}
              className="flex items-center justify-between gap-3 bg-surface border border-border rounded-lg px-4 py-3 hover:border-accent/50"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
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
