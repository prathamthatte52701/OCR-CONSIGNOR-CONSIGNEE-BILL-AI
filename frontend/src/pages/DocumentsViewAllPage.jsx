import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useDocumentsList } from "../hooks/useDocumentsQueries";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";

const PAGE_SIZE = 50;

// Read-only, spreadsheet-style overview: one row per document, every key header + total field
// as its own column, so a whole page of documents can be scanned and compared at a glance.
// Editing stays on the detail page - nothing here is editable. Sorting is client-side and
// applies to the rows of the page currently loaded.
const COLUMNS = [
  { key: "invoiceNo", label: "Invoice No", getValue: (d) => d.invoiceNo || "" },
  { key: "fiDoc", label: "FI Doc.", getValue: (d) => d.fiDoc || "" },
  { key: "challanDate", label: "Date", getValue: (d) => d.challanDate || "" },
  { key: "consigneeCode", label: "Consignee Code", getValue: (d) => d.consigneeCode || "" },
  { key: "consignee", label: "Consignee", getValue: (d) => d.consignee || "" },
  { key: "consigneeGstin", label: "Consignee GSTIN", getValue: (d) => d.consigneeGstin || "" },
  { key: "consigneePan", label: "Consignee PAN", getValue: (d) => d.consigneePan || "" },
  { key: "consignorPoNo", label: "PO No.", getValue: (d) => d.consignorPoNo || "" },
  { key: "requestNo", label: "Request No.", getValue: (d) => d.requestNo || "" },
  { key: "consignorGstin", label: "Consignor GSTIN", getValue: (d) => d.consignorGstin || "" },
  { key: "consignorPan", label: "Consignor PAN", getValue: (d) => d.consignorPan || "" },
  { key: "lineItemCount", label: "Items", getValue: (d) => String((d.lineItems || []).length) },
  { key: "totalBasicAmount", label: "Total Basic", getValue: (d) => d.totalBasicAmount || "" },
  { key: "totalAmount", label: "Total Amount", getValue: (d) => d.totalAmount || "" },
  { key: "uploadStatus", label: "Status", getValue: (d) => d.uploadStatus || "" },
  { key: "createdAt", label: "Uploaded", getValue: (d) => d.createdAt || "" },
];

export default function DocumentsViewAllPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10) || 1);
  const query = useDocumentsList({ page: String(page), limit: String(PAGE_SIZE) });
  const documents = query.data?.items;

  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");

  const rows = useMemo(() => {
    if (!documents) return [];
    if (!sortKey) return documents;
    const col = COLUMNS.find((c) => c.key === sortKey);
    const numeric = sortKey === "lineItemCount";
    return [...documents].sort((a, b) => {
      const av = col.getValue(a);
      const bv = col.getValue(b);
      const cmp = numeric ? Number(av) - Number(bv) : String(av).localeCompare(String(bv));
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [documents, sortKey, sortDir]);

  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const goToPage = (p) => setSearchParams({ page: String(p) });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">View All Details</h1>
          <p className="text-xs text-text-muted mt-1">
            {query.isLoading ? "Loading..." : `${total} document${total !== 1 ? "s" : ""} · read-only`}
          </p>
        </div>
        <Link
          to="/documents"
          className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
        >
          Back to Documents
        </Link>
      </div>

      {query.isLoading ? (
        <LoadingState message="Loading documents..." />
      ) : query.isError ? (
        <p className="text-sm text-danger py-10 text-center">
          {query.error?.userMessage || "Could not load your documents. Please try again."}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-text-muted py-10 text-center">No documents yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-surface-raised text-left text-text-muted">
                <th className="px-3 py-2 font-medium">#</th>
                {COLUMNS.map((col) => (
                  <th key={col.key} className="px-3 py-2 font-medium whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      className="inline-flex items-center gap-1 hover:text-accent"
                    >
                      {col.label}
                      {sortKey === col.key && <span>{sortDir === "asc" ? "↑" : "↓"}</span>}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((doc, index) => (
                <tr key={doc.id} className="border-t border-border hover:bg-surface-raised/50">
                  <td className="px-3 py-2 text-text-muted">{(page - 1) * PAGE_SIZE + index + 1}</td>
                  {COLUMNS.map((col) => {
                    const value = col.key === "createdAt" ? formatIST(doc.createdAt) : col.getValue(doc);
                    return (
                      <td key={col.key} className="px-3 py-2 whitespace-nowrap">
                        {col.key === "invoiceNo" ? (
                          <Link to={`/documents/${doc.id}`} className="text-accent hover:underline">
                            {value || "(no invoice no.)"}
                          </Link>
                        ) : (
                          value || "-"
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
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
