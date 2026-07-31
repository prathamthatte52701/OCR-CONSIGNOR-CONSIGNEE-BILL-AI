import { Link } from "react-router-dom";
import { FileStack, CheckCircle2, XCircle, CalendarClock, AlertTriangle, Layers } from "lucide-react";
import { useDocumentsList, useDocumentStats } from "../hooks/useDocumentsQueries";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";

function StatCard({ icon: Icon, label, value, tone = "text-text" }) {
  return (
    <div className="bg-surface border border-border rounded-lg p-4">
      <div className="flex items-center gap-2 text-text-muted text-xs mb-2">
        <Icon size={14} />
        {label}
      </div>
      <p className={`text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const statsQuery = useDocumentStats();
  const recentQuery = useDocumentsList({ page: 1, limit: 5 });

  if (statsQuery.isLoading) return <LoadingState message="Loading dashboard..." />;

  const stats = statsQuery.data;
  const recent = recentQuery.data?.items ?? [];

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Dashboard</h1>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
        <StatCard icon={FileStack} label="Total" value={stats.total} />
        <StatCard icon={CheckCircle2} label="Processed" value={stats.processed} tone="text-accent" />
        <StatCard icon={XCircle} label="Failed" value={stats.failed} tone="text-danger" />
        <StatCard icon={CalendarClock} label="Processed Today" value={stats.processedToday} />
        <StatCard icon={AlertTriangle} label="Low Confidence" value={stats.lowConfidence} tone="text-warning" />
        <StatCard icon={Layers} label="Multi-page" value={stats.multiPage} />
      </div>

      <h2 className="text-sm font-semibold text-text-muted mb-3">Recent documents</h2>
      <div className="space-y-2">
        {recent.map((doc) => (
          <Link
            key={doc.id}
            to={`/documents/${doc.id}`}
            className="flex items-center justify-between bg-surface border border-border rounded-lg px-4 py-3 hover:border-accent/50"
          >
            <span className="text-sm font-medium">{doc.invoiceNo || "(no invoice no.)"}</span>
            <span className="text-xs text-text-muted">{formatIST(doc.createdAt)}</span>
          </Link>
        ))}
        {recent.length === 0 && (
          <p className="text-sm text-text-muted py-6 text-center">
            No documents yet. <Link to="/upload" className="text-accent">Upload one</Link> to get started.
          </p>
        )}
      </div>
    </div>
  );
}
