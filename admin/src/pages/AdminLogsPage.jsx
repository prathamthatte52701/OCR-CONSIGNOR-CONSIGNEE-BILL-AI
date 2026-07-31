import { useEffect, useState } from "react";
import { toast } from "sonner";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import PaginationControls from "../components/PaginationControls";
import { formatIST } from "../lib/formatDate";

const LIMIT = 30;

export default function AdminLogsPage() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    adminApi
      .logs({ page, limit: LIMIT, action: action || undefined })
      .then(setData)
      .catch((err) => toast.error(err.userMessage))
      .finally(() => setLoading(false));
  }, [page, action]);

  if (loading && !data) return <LoadingState message="Loading logs..." />;

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / LIMIT));

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Audit Logs ({data?.total ?? 0})</h1>

      <input
        placeholder="Filter by action (e.g. login, document_deleted)"
        value={action}
        onChange={(e) => {
          setAction(e.target.value);
          setPage(1);
        }}
        className="mb-4 w-full max-w-sm rounded border border-border bg-bg px-3 py-2 text-sm"
      />

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-raised text-left text-xs text-text-muted">
              <th className="px-3 py-2 font-medium">Time</th>
              <th className="px-3 py-2 font-medium">User</th>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="px-3 py-2 font-medium">Context</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((log) => (
              <tr key={log.id} className="border-t border-border">
                <td className="px-3 py-2 text-xs whitespace-nowrap">{formatIST(log.createdAt)}</td>
                <td className="px-3 py-2 text-xs">{log.username || "-"}</td>
                <td className="px-3 py-2 text-xs font-mono">{log.action}</td>
                <td className="px-3 py-2 text-xs text-text-muted truncate max-w-xs">
                  {JSON.stringify(log.context)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <PaginationControls page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  );
}
