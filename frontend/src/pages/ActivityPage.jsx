import { useState } from "react";
import { Link } from "react-router-dom";
import { History } from "lucide-react";
import { useActivity } from "../hooks/useActivity";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";
import { cn } from "../lib/utils";

const PAGE_SIZE = 40;

const CHIPS = [
  { value: "all", label: "All" },
  { value: "documents", label: "Documents" },
  { value: "account", label: "Account" },
];

const ACTION_LABELS = {
  login: "Logged in",
  password_change: "Password changed",
  password_reset_requested: "Password reset requested",
  document_uploaded: "Document uploaded",
  document_reprocessed: "Document reprocessed",
  document_deleted: "Document deleted",
  document_file_purged: "Original files purged",
  document_corrected: "Document edited",
  documents_download_all: "Bulk download",
};

const ACTION_BADGE = {
  document_deleted: "bg-danger/15 text-danger",
  document_file_purged: "bg-warning/15 text-warning",
};

// Same wording as the document detail page (Consignee/Consignor prefixed where that page's
// label is only unique inside its own section).
const FIELD_LABELS = {
  consigneeCode: "Consignee Code",
  consignee: "Consignee",
  consigneeAddress: "Consignee Address",
  consigneePincode: "Consignee Pincode",
  consigneeStateCode: "Consignee State Code",
  consigneeStateName: "Consignee State Name",
  consigneeGstin: "Consignee GSTIN",
  consigneePan: "Consignee PAN",
  invoiceNo: "Invoice No",
  fiDoc: "FI Doc.",
  challanDate: "Date",
  reason: "Reason",
  consignorName: "Consignor Name",
  consignorAddress: "Consignor Address",
  consignorPincode: "Consignor Pincode",
  consignorStateCode: "Consignor State Code",
  consignorStateName: "Consignor State Name",
  consignorGstin: "Consignor GSTIN",
  consignorPan: "Consignor PAN",
  consignorPoNo: "PO No.",
  requestNo: "Request No.",
  irnNo: "IRN No.",
  totalBasicAmount: "Total Basic Amount",
  cgstRate: "CGST Rate",
  cgstAmount: "CGST Amount",
  sgstRate: "SGST Rate",
  sgstAmount: "SGST Amount",
  igstRate: "IGST Rate",
  igstAmount: "IGST Amount",
  totalAmount: "Total Amount",
  srNo: "Sr No",
  description: "Description",
  hsnSac: "HSN/SAC",
  basic: "Basic",
  quantity: "Quantity",
  amount: "Amount",
};

function fieldLabel(field) {
  const m = /^lineItems\.(\d+)\.(\w+)$/.exec(field || "");
  if (m) return `Item ${Number(m[1]) + 1} ${FIELD_LABELS[m[2]] || m[2]}`;
  return FIELD_LABELS[field] || field;
}

function describeAction(entry) {
  const ctx = entry.context || {};
  if (entry.action === "documents_download_all") {
    const n = ctx.included ?? ctx.requested;
    return n != null ? `Bulk download (${n} ${n === 1 ? "file" : "files"})` : "Bulk download";
  }
  return ACTION_LABELS[entry.action] || entry.action.replace(/_/g, " ");
}

function DocumentCell({ entry }) {
  if (!entry.action.startsWith("document") || entry.action === "documents_download_all") {
    return null;
  }
  const doc = entry.document;
  const ctx = entry.context || {};
  if (doc) {
    const text = [doc.invoiceNo, doc.consignee].filter(Boolean).join(" - ") || "Document";
    return (
      <Link to={`/documents/${doc.id}`} className="text-xs text-accent hover:underline truncate">
        {text}
      </Link>
    );
  }
  const text = [ctx.invoiceNo, ctx.consignee].filter(Boolean).join(" - ");
  return <span className="text-xs text-text-muted truncate">{text || "No longer available"}</span>;
}

export default function ActivityPage() {
  const [page, setPage] = useState(1);
  const [type, setType] = useState("documents");
  const query = useActivity({ type, page, limit: PAGE_SIZE });

  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const pickType = (value) => {
    setType(value);
    setPage(1);
  };

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">My Activity</h1>

      <div className="flex flex-wrap gap-2 mb-4">
        {CHIPS.map((chip) => (
          <button
            key={chip.value}
            type="button"
            onClick={() => pickType(chip.value)}
            aria-pressed={type === chip.value}
            className={cn(
              "px-3 py-1 rounded-full border text-xs font-medium",
              type === chip.value
                ? "bg-accent text-bg border-accent"
                : "border-border text-text-muted hover:border-accent/50"
            )}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {query.data && (
        <p className="mb-3 text-xs text-text-muted">
          {total} {total === 1 ? "activity" : "activities"}
        </p>
      )}

      {query.isError && query.data && (
        <p className="flex items-center gap-2 mb-3 text-xs text-danger">
          Could not refresh. Try again
          <button
            type="button"
            onClick={() => query.refetch()}
            className="rounded border border-border px-2 py-0.5 text-text hover:border-accent/50"
          >
            Retry
          </button>
        </p>
      )}

      {query.isLoading ? (
        <LoadingState message="Loading activity..." />
      ) : query.isError && !query.data ? (
        <div className="text-center py-10">
          <p className="text-sm text-danger mb-3">
            {query.error?.userMessage || "Could not load your activity."}
          </p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
          >
            Try again
          </button>
        </div>
      ) : query.data?.items.length === 0 ? (
        <p className="text-sm text-text-muted py-10 text-center">No activity found.</p>
      ) : (
        <div className="space-y-2">
          {query.data.items.map((entry) => (
            <div
              key={entry.id}
              className="flex items-center justify-between gap-3 bg-surface border border-border rounded-lg px-4 py-3"
            >
              <div className="flex items-center gap-2 min-w-0">
                <History size={14} className="text-text-muted shrink-0" />
                <span
                  className={cn(
                    "text-sm shrink-0",
                    ACTION_BADGE[entry.action] && `px-2 py-0.5 rounded-full text-xs ${ACTION_BADGE[entry.action]}`
                  )}
                >
                  {describeAction(entry)}
                </span>
                {entry.context?.byAdmin === true && (
                  <span className="text-xs px-1.5 py-0.5 rounded-full bg-surface-raised text-text-muted shrink-0">
                    by admin
                  </span>
                )}
                {entry.action === "document_corrected" && entry.context?.field && (
                  <span className="text-xs text-text-muted shrink-0">
                    {fieldLabel(entry.context.field)}
                  </span>
                )}
                <DocumentCell entry={entry} />
              </div>
              <span className="text-xs text-text-muted shrink-0">{formatIST(entry.createdAt)}</span>
            </div>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-6 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="px-3 py-1.5 rounded border border-border disabled:opacity-30"
          >
            Previous
          </button>
          <span className="text-text-muted">
            Page {page} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="px-3 py-1.5 rounded border border-border disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
