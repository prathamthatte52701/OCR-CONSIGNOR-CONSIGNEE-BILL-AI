import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useDocumentsList } from "../hooks/useDocumentsQueries";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";
import {
  apiParamsFromFilters,
  describeFilters,
  filtersFromSearchParams,
  hasActiveFilters,
  parsePage,
  urlParamsFromFilters,
} from "../lib/documentFilters";

const PAGE_SIZE = 50;

// Read-only, spreadsheet-style overview: one row per document, every key header + total field
// as its own column, so a whole page of documents can be scanned and compared at a glance.
// Editing stays on the detail page - nothing here is editable. Columns with `sortKey` sort on
// the server (sort/order in the URL, across every page); the others are plain text headers.
const COLUMNS = [
  { key: "invoiceNo", label: "Invoice No", sortKey: "invoiceNo", getValue: (d) => d.invoiceNo || "" },
  { key: "fiDoc", label: "FI Doc.", getValue: (d) => d.fiDoc || "" },
  { key: "challanDate", label: "Date", sortKey: "challanDate", getValue: (d) => d.challanDate || "" },
  {
    key: "consigneeCode",
    label: "Consignee Code",
    sortKey: "consigneeCode",
    getValue: (d) => d.consigneeCode || "",
  },
  { key: "consignee", label: "Consignee", sortKey: "consignee", getValue: (d) => d.consignee || "" },
  { key: "consigneeGstin", label: "Consignee GSTIN", getValue: (d) => d.consigneeGstin || "" },
  { key: "consigneePan", label: "Consignee PAN", getValue: (d) => d.consigneePan || "" },
  { key: "consignorPoNo", label: "PO No.", getValue: (d) => d.consignorPoNo || "" },
  { key: "requestNo", label: "Request No.", getValue: (d) => d.requestNo || "" },
  { key: "consignorGstin", label: "Consignor GSTIN", getValue: (d) => d.consignorGstin || "" },
  { key: "consignorPan", label: "Consignor PAN", getValue: (d) => d.consignorPan || "" },
  { key: "lineItemCount", label: "Items", getValue: (d) => String((d.lineItems || []).length) },
  { key: "totalBasicAmount", label: "Total Basic", getValue: (d) => d.totalBasicAmount || "" },
  { key: "totalAmount", label: "Total Amount", getValue: (d) => d.totalAmount || "" },
  { key: "uploadStatus", label: "Status", sortKey: "uploadStatus", getValue: (d) => d.uploadStatus || "" },
  { key: "createdAt", label: "Uploaded", sortKey: "createdAt", getValue: (d) => d.createdAt || "" },
];
const SORT_KEYS = new Set(COLUMNS.map((c) => c.sortKey).filter(Boolean));

export default function DocumentsViewAllPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = filtersFromSearchParams(searchParams);
  const page = parsePage(searchParams);
  const sort = SORT_KEYS.has(searchParams.get("sort")) ? searchParams.get("sort") : "";
  const order = searchParams.get("order") === "desc" ? "desc" : "asc";

  const query = useDocumentsList({
    ...apiParamsFromFilters(filters),
    ...(sort ? { sort, order } : {}),
    page,
    limit: PAGE_SIZE,
  });
  const rows = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // A page past the end goes to the last real page.
  useEffect(() => {
    if (query.data && !query.isPlaceholderData && page > totalPages) {
      setSearchParams(
        { ...Object.fromEntries(searchParams), page: String(totalPages) },
        { replace: true }
      );
    }
  }, [query.data, query.isPlaceholderData, page, totalPages, searchParams, setSearchParams]);

  const withParams = (extra) => ({ ...Object.fromEntries(searchParams), ...extra });

  // Sorting is done by the server; changing it goes back to page 1.
  const toggleSort = (key) => {
    const nextOrder = sort === key && order === "asc" ? "desc" : "asc";
    setSearchParams(withParams({ sort: key, order: nextOrder, page: "1" }));
  };

  const goToPage = (p) => setSearchParams(withParams({ page: String(p) }));

  const filterDescription = describeFilters(filters);
  const backLink = `/documents${
    hasActiveFilters(filters) ? `?${new URLSearchParams(urlParamsFromFilters(filters))}` : ""
  }`;

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
          to={backLink}
          className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
        >
          Back to Documents
        </Link>
      </div>

      {filterDescription.length > 0 && (
        <p className="flex flex-wrap items-center gap-2 mb-4 text-xs text-text-muted">
          <span>Filtered by {filterDescription.join(", ")}</span>
          <button
            type="button"
            onClick={() => setSearchParams(sort ? { sort, order, page: "1" } : { page: "1" })}
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
      ) : rows.length === 0 ? (
        <p className="text-sm text-text-muted py-10 text-center">No documents found.</p>
      ) : (
        <div
          className={`overflow-x-auto rounded-lg border border-border ${
            query.isPlaceholderData ? "opacity-50" : ""
          }`}
        >
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-surface-raised text-left text-text-muted">
                <th className="px-3 py-2 font-medium">#</th>
                {COLUMNS.map((col) => (
                  <th key={col.key} className="px-3 py-2 font-medium whitespace-nowrap">
                    {col.sortKey ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(col.sortKey)}
                        className="inline-flex items-center gap-1 hover:text-accent"
                      >
                        {col.label}
                        {sort === col.sortKey && <span>{order === "asc" ? "↑" : "↓"}</span>}
                      </button>
                    ) : (
                      col.label
                    )}
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
