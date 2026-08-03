import { useState } from "react";
import { History } from "lucide-react";
import { useActivity } from "../hooks/useActivity";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";

const PAGE_SIZE = 40;

const ACTION_LABELS = {
  signup: "Account created",
  login: "Logged in",
  password_change: "Password changed",
  password_reset: "Password reset",
  document_uploaded: "Document uploaded",
  document_reprocessed: "Document reprocessed",
  document_deleted: "Document deleted",
  document_file_purged: "Original files purged",
  document_corrected: "Document field corrected",
};

function describeAction(action) {
  return ACTION_LABELS[action] || action.replace(/_/g, " ");
}

export default function ActivityPage() {
  const [page, setPage] = useState(1);
  const query = useActivity({ page, limit: PAGE_SIZE });

  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">My Activity</h1>

      {query.isLoading ? (
        <LoadingState message="Loading activity..." />
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
                <span className="text-sm truncate capitalize">{describeAction(entry.action)}</span>
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
