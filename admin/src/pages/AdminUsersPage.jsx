import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import PaginationControls from "../components/PaginationControls";
import { formatIST } from "../lib/formatDate";

const LIMIT = 30;

export default function AdminUsersPage() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    adminApi
      .users({ page, limit: LIMIT })
      .then(setData)
      .catch((err) => toast.error(err.userMessage))
      .finally(() => setLoading(false));
  };

  useEffect(load, [page]);

  if (loading && !data) return <LoadingState message="Loading users..." />;

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / LIMIT));

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Users ({data?.total ?? 0})</h1>

      <div className="space-y-2">
        {data?.items.map((user) => (
          <Link
            key={user.id}
            to={`/users/${user.id}`}
            className="flex items-center justify-between bg-surface border border-border rounded-lg px-4 py-3 hover:border-accent/50"
          >
            <div>
              <p className="text-sm font-medium">{user.username}</p>
              <p className="text-xs text-text-muted">{user.email}</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              <span className={user.role === "admin" ? "text-accent font-medium" : ""}>{user.role}</span>
              <span>{formatIST(user.createdAt)}</span>
            </div>
          </Link>
        ))}
      </div>

      <PaginationControls page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  );
}
