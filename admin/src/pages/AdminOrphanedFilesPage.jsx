import { useEffect, useState } from "react";
import { toast } from "sonner";
import { RefreshCw, X } from "lucide-react";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import PaginationControls from "../components/PaginationControls";
import { formatIST } from "../lib/formatDate";

const LIMIT = 30;

export default function AdminOrphanedFilesPage() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = () => {
    setLoading(true);
    adminApi
      .orphanedFiles({ page, limit: LIMIT })
      .then(setData)
      .catch((err) => toast.error(err.userMessage))
      .finally(() => setLoading(false));
  };

  useEffect(load, [page]);

  const handleRetry = async (id) => {
    setBusyId(id);
    try {
      const res = await adminApi.retryOrphanedFile(id);
      toast.success(res.message || "File deleted.");
      load();
    } catch (err) {
      toast.error(err.userMessage || "Retry failed.");
    } finally {
      setBusyId(null);
    }
  };

  const handleDismiss = async (id) => {
    setBusyId(id);
    try {
      await adminApi.dismissOrphanedFile(id);
      toast.success("Dismissed.");
      load();
    } catch (err) {
      toast.error(err.userMessage || "Could not dismiss.");
    } finally {
      setBusyId(null);
    }
  };

  if (loading && !data) return <LoadingState message="Loading orphaned files..." />;

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / LIMIT));

  return (
    <div>
      <h1 className="text-xl font-semibold mb-1">Orphaned Files ({data?.total ?? 0})</h1>
      <p className="text-sm text-text-muted mb-4">
        GridFS files whose delete failed (e.g. transient Mongo error). Retry re-attempts the
        delete; Dismiss clears the record without retrying.
      </p>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-raised text-left text-xs text-text-muted">
              <th className="px-3 py-2 font-medium">Last Attempt</th>
              <th className="px-3 py-2 font-medium">File Id</th>
              <th className="px-3 py-2 font-medium">Document Id</th>
              <th className="px-3 py-2 font-medium">User Id</th>
              <th className="px-3 py-2 font-medium">Last Error</th>
              <th className="px-3 py-2 font-medium">Attempts</th>
              <th className="px-3 py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((record) => (
              <tr key={record.id} className="border-t border-border">
                <td className="px-3 py-2 text-xs whitespace-nowrap">
                  {formatIST(record.lastAttemptAt)}
                </td>
                <td className="px-3 py-2 text-xs font-mono">{record.fileId}</td>
                <td className="px-3 py-2 text-xs font-mono">{record.documentId || "-"}</td>
                <td className="px-3 py-2 text-xs font-mono">{record.userId || "-"}</td>
                <td className="px-3 py-2 text-xs text-text-muted truncate max-w-xs">
                  {record.lastError}
                </td>
                <td className="px-3 py-2 text-xs">{record.attemptCount}</td>
                <td className="px-3 py-2 text-xs whitespace-nowrap">
                  <div className="flex gap-2 justify-end">
                    <button
                      onClick={() => handleRetry(record.id)}
                      disabled={busyId === record.id}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-accent/40 text-accent hover:bg-accent/10 disabled:opacity-40"
                    >
                      <RefreshCw size={12} /> Retry
                    </button>
                    <button
                      onClick={() => handleDismiss(record.id)}
                      disabled={busyId === record.id}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-danger/40 text-danger hover:bg-danger/10 disabled:opacity-40"
                    >
                      <X size={12} /> Dismiss
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {data?.items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-text-muted">
                  No orphaned files.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <PaginationControls page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  );
}
