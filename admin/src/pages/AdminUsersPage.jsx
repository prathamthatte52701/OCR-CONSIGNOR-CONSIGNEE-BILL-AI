import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { adminApi } from "../api/admin";
import ConfirmModal from "../components/ConfirmModal";
import LoadingState from "../components/LoadingState";
import PaginationControls from "../components/PaginationControls";
import { formatIST } from "../lib/formatDate";

const LIMIT = 30;

const TABS = [
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "all", label: "All" },
];

const STATUS_STYLE = {
  pending: "text-warning",
  approved: "text-success",
  rejected: "text-danger",
};

// Which actions each status offers. Approve is instant (easy to undo); anything that locks a user
// out or destroys data goes through a confirmation first.
function actionsFor(user) {
  if (user.role === "admin") return []; // admins can never be rejected / revoked here
  if (user.status === "pending") return ["approve", "reject"];
  if (user.status === "rejected") return ["reapprove", "delete"];
  return ["revoke"];
}

const ACTION_LABEL = {
  approve: "Approve",
  reject: "Reject",
  reapprove: "Re-approve",
  revoke: "Revoke",
  delete: "Delete",
};

const ACTION_STYLE = {
  approve: "bg-emerald-600 hover:bg-emerald-700",
  reapprove: "bg-emerald-600 hover:bg-emerald-700",
  reject: "bg-red-600 hover:bg-red-700",
  revoke: "bg-red-600 hover:bg-red-700",
  delete: "bg-red-700 hover:bg-red-800",
};

const CONFIRM_COPY = {
  reject: (u) => ({
    title: "Reject this sign-up?",
    message: `${u.username} (${u.email}) will not be able to log in. You can re-approve later.`,
    confirmLabel: "Reject",
  }),
  revoke: (u) => ({
    title: "Revoke access?",
    message: `${u.username} (${u.email}) will be logged out everywhere and locked out. You can re-approve later.`,
    confirmLabel: "Revoke",
  }),
  delete: (u) => ({
    title: "Permanently delete this user?",
    message: `${u.username} (${u.email}) and ALL their documents, files and activity will be permanently deleted. There is no undo.`,
    confirmLabel: "Delete",
  }),
};

export default function AdminUsersPage() {
  const [tab, setTab] = useState("pending");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [confirm, setConfirm] = useState(null); // { user, action }
  const inFlight = useRef(false); // blocks a double click from firing the same request twice

  const load = () => {
    setLoading(true);
    adminApi
      .users({ page, limit: LIMIT, ...(tab === "all" ? {} : { status: tab }) })
      .then(setData)
      .catch((err) => toast.error(err.userMessage))
      .finally(() => setLoading(false));
  };

  useEffect(load, [page, tab]);

  const changeTab = (key) => {
    setTab(key);
    setPage(1);
  };

  const run = async (user, action) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusyId(user.id);
    try {
      if (action === "approve" || action === "reapprove") await adminApi.approveUser(user.id);
      else if (action === "reject" || action === "revoke") await adminApi.rejectUser(user.id);
      else await adminApi.deleteUser(user.id);
      toast.success(`${ACTION_LABEL[action]}: ${user.username}`);
      load();
    } catch (err) {
      toast.error(err.userMessage);
    } finally {
      inFlight.current = false;
      setBusyId(null);
    }
  };

  // The buttons sit inside a row that is itself a <Link>, so a click must not navigate.
  const onAction = (event, user, action) => {
    event.preventDefault();
    event.stopPropagation();
    if (CONFIRM_COPY[action]) setConfirm({ user, action });
    else run(user, action);
  };

  if (loading && !data) return <LoadingState message="Loading users..." />;

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / LIMIT));
  const copy = confirm ? CONFIRM_COPY[confirm.action](confirm.user) : null;

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Users ({data?.total ?? 0})</h1>

      <div className="flex gap-2 mb-4 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => changeTab(t.key)}
            className={`px-3 py-2 text-sm -mb-px border-b-2 ${
              tab === t.key
                ? "border-accent text-accent font-medium"
                : "border-transparent text-text-muted hover:text-text"
            }`}
          >
            {t.label}
            {t.key === "pending" && data?.pendingCount > 0 && (
              <span
                data-testid="pending-badge"
                className="ml-1.5 rounded-full bg-warning px-1.5 py-0.5 text-[10px] font-semibold text-bg"
              >
                {data.pendingCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {data?.items.length === 0 && (
        <p className="text-sm text-text-muted py-6 text-center">No users in this list.</p>
      )}

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
              <span className={STATUS_STYLE[user.status] ?? ""}>{user.status}</span>
              <span className={user.role === "admin" ? "text-accent font-medium" : ""}>{user.role}</span>
              <span>{formatIST(user.createdAt)}</span>
              {actionsFor(user).map((action) => (
                <button
                  key={action}
                  type="button"
                  disabled={busyId === user.id}
                  onClick={(e) => onAction(e, user, action)}
                  className={`rounded px-2.5 py-1 text-white disabled:opacity-50 ${ACTION_STYLE[action]}`}
                >
                  {ACTION_LABEL[action]}
                </button>
              ))}
            </div>
          </Link>
        ))}
      </div>

      <PaginationControls page={page} totalPages={totalPages} onChange={setPage} />

      <ConfirmModal
        open={Boolean(confirm)}
        title={copy?.title}
        message={copy?.message}
        severity="critical"
        confirmLabel={copy?.confirmLabel}
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          const { user, action } = confirm;
          setConfirm(null);
          run(user, action);
        }}
      />
    </div>
  );
}
