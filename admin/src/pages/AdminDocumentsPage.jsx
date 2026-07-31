import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import PaginationControls from "../components/PaginationControls";
import { formatIST } from "../lib/formatDate";

const LIMIT = 30;

export default function AdminDocumentsPage() {
  const [searchParams] = useSearchParams();
  const userId = searchParams.get("userId") || undefined;
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    adminApi
      .documents({ userId, page, limit: LIMIT })
      .then(setData)
      .catch((err) => toast.error(err.userMessage))
      .finally(() => setLoading(false));
  };

  useEffect(load, [page, userId]);

  if (loading && !data) return <LoadingState message="Loading documents..." />;

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / LIMIT));

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">
        Documents ({data?.total ?? 0}){userId && <span className="text-sm text-text-muted"> - filtered by user</span>}
      </h1>

      <div className="space-y-2">
        {data?.items.map((doc) => (
          <Link
            key={doc.id}
            to={`/documents/${doc.id}`}
            className="flex items-center justify-between bg-surface border border-border rounded-lg px-4 py-3 hover:border-accent/50"
          >
            <div>
              <p className="text-sm font-medium">{doc.invoiceNo || "(no invoice no.)"}</p>
              <p className="text-xs text-text-muted">
                {doc.ownerUsername} &middot; {doc.consignee || "-"} &middot; {formatIST(doc.createdAt)}
              </p>
            </div>
            <span className="text-xs px-2 py-0.5 rounded-full bg-surface-raised text-text-muted">
              {doc.uploadStatus}
            </span>
          </Link>
        ))}
        {data?.items.length === 0 && <p className="text-sm text-text-muted py-10 text-center">No documents.</p>}
      </div>

      <PaginationControls page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  );
}
