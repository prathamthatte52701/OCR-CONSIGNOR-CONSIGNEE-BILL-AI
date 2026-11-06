import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  FileStack,
  CheckCircle2,
  XCircle,
  CalendarClock,
  AlertTriangle,
  Layers,
  Loader2,
  Search,
} from "lucide-react";
import {
  useDocumentsList,
  useDocumentStats,
  useDocumentStorage,
} from "../hooks/useDocumentsQueries";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";
import { cn } from "../lib/utils";
import { needsAttention } from "../lib/needsAttention";

const STATUS_STYLES = {
  processed: "bg-accent/15 text-accent",
  processing: "bg-warning/15 text-warning",
  uploaded: "bg-warning/15 text-warning",
  failed: "bg-danger/15 text-danger",
};
const CARD = "bg-surface border border-border rounded-lg p-4";
const REFRESH_MS = 5000;

function StatCard({ icon: Icon, label, value, tone = "text-text", to, title }) {
  const body = (
    <>
      <div className="flex items-center gap-2 text-text-muted text-xs mb-2">
        <Icon size={14} />
        {label}
      </div>
      <p className={`text-2xl font-semibold ${tone}`}>{value}</p>
    </>
  );
  return to ? (
    <Link to={to} title={title} className={cn(CARD, "block hover:border-accent/50")}>
      {body}
    </Link>
  ) : (
    <div className={CARD}>{body}</div>
  );
}

function ErrorBox({ message, onRetry }) {
  return (
    <div className="text-center py-6">
      <p className="text-sm text-danger mb-3">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
      >
        Retry
      </button>
    </div>
  );
}

function formatBytes(n) {
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [searchText, setSearchText] = useState("");
  // Poll every 5 s while something is processing, stop when nothing is (React Query also
  // pauses polling in a hidden tab by default).
  const statsQuery = useDocumentStats({
    refetchInterval: (q) => (q.state.data?.processing > 0 ? REFRESH_MS : false),
  });
  const processing = statsQuery.data?.processing ?? 0;
  const recentQuery = useDocumentsList(
    { page: 1, limit: 5 },
    { refetchInterval: processing > 0 ? REFRESH_MS : false }
  );
  const storageQuery = useDocumentStorage();

  const runSearch = (e) => {
    e.preventDefault();
    const text = searchText.trim();
    navigate(text ? `/documents?search=${encodeURIComponent(text)}&page=1` : "/documents");
  };

  if (statsQuery.isLoading) return <LoadingState message="Loading dashboard..." />;
  if (statsQuery.isError || !statsQuery.data) {
    return (
      <div>
        <h1 className="text-xl font-semibold mb-4">Dashboard</h1>
        <ErrorBox
          message={statsQuery.error?.userMessage || "Could not load the dashboard numbers."}
          onRetry={() => statsQuery.refetch()}
        />
      </div>
    );
  }

  const stats = statsQuery.data;
  const recent = recentQuery.data?.items ?? [];
  const finished = stats.processed + stats.failed;
  const successRate = finished > 0 ? Math.round((stats.processed / finished) * 100) : null;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <form onSubmit={runSearch} className="flex gap-2">
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            maxLength={100}
            placeholder="Search invoice, consignee or code"
            className="w-64 rounded border border-border bg-surface px-3 py-1.5 text-sm"
          />
          <button
            type="submit"
            className="inline-flex items-center gap-1 rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
          >
            <Search size={14} /> Search
          </button>
        </form>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
        <StatCard icon={FileStack} label="Total" value={stats.total} to="/documents" />
        <StatCard
          icon={CheckCircle2}
          label="Processed"
          value={stats.processed}
          tone="text-accent"
          to="/documents?status=processed"
        />
        <StatCard
          icon={XCircle}
          label="Failed"
          value={stats.failed}
          tone="text-danger"
          to="/documents?status=failed"
        />
        <StatCard
          icon={CalendarClock}
          label="Processed Today"
          value={stats.processedToday}
          to="/documents?range=today"
          title="Opens documents uploaded today"
        />
        <StatCard
          icon={AlertTriangle}
          label="Needs review"
          value={stats.needsReview}
          tone="text-warning"
          to="/documents?needsReview=1"
        />
        <StatCard icon={Layers} label="Multi-page" value={stats.multiPage} />
        <StatCard icon={Loader2} label="Processing now" value={stats.processing} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 mb-8">
        <div className={CARD}>
          <h2 className="text-sm font-semibold text-text-muted mb-3">Quality</h2>
          <div className="flex items-center justify-between text-xs text-text-muted mb-1">
            <span>Success rate</span>
            <span className="text-text font-semibold text-sm">
              {successRate === null ? "-" : `${successRate}%`}
            </span>
          </div>
          <div className="h-2 rounded-full bg-surface-raised overflow-hidden mb-3">
            <div className="h-full bg-accent" style={{ width: `${successRate ?? 0}%` }} />
          </div>
          <p className="text-xs text-text-muted">
            {stats.processed} processed &middot; {stats.failed} failed &middot; Documents you
            corrected: {stats.corrected}
          </p>
        </div>
        <div className={CARD}>
          <h2 className="text-sm font-semibold text-text-muted mb-3">Stored files</h2>
          {storageQuery.isError ? (
            <p className="text-xs text-text-muted">Storage info unavailable.</p>
          ) : (
            <p className="text-sm">
              Original files stored:{" "}
              <span className="font-semibold">
                {storageQuery.data
                  ? `${storageQuery.data.documents} documents - ${formatBytes(storageQuery.data.bytes)}`
                  : "..."}
              </span>
            </p>
          )}
          <Link to="/documents" className="text-xs text-accent mt-2 inline-block">
            Open documents
          </Link>
        </div>
      </div>

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-text-muted">Recent documents</h2>
        <Link to="/documents" className="text-xs text-accent">
          View all
        </Link>
      </div>
      {recentQuery.isError ? (
        <ErrorBox
          message={recentQuery.error?.userMessage || "Could not load recent documents."}
          onRetry={() => recentQuery.refetch()}
        />
      ) : (
        <div className="space-y-2">
          {recent.map((doc) => (
            <Link
              key={doc.id}
              to={`/documents/${doc.id}`}
              className="flex items-center justify-between gap-3 bg-surface border border-border rounded-lg px-4 py-3 hover:border-accent/50"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">
                    {doc.invoiceNo || "(no invoice no.)"}
                  </span>
                  {needsAttention(doc) && (
                    <AlertTriangle size={14} className="text-warning shrink-0" />
                  )}
                </div>
                <p className="text-xs text-text-muted truncate">
                  {doc.consignee || "-"} - {doc.consigneeCode || "-"} &middot;{" "}
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
          {!recentQuery.isLoading && recent.length === 0 && (
            <p className="text-sm text-text-muted py-6 text-center">
              No documents yet. <Link to="/upload" className="text-accent">Upload one</Link> to get
              started.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
