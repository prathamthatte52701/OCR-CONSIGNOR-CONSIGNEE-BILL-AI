import { useEffect, useState } from "react";
import { Users, FileStack, CheckCircle2, XCircle, AlertTriangle, Layers, Activity } from "lucide-react";
import { toast } from "sonner";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import NukeDialog from "../components/NukeDialog";

const NUKE_GLOBAL_PHRASE = "NUKE ALL";

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

export default function AdminDashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [nukeOpen, setNukeOpen] = useState(false);
  const [nukeBusy, setNukeBusy] = useState(false);

  const loadTelemetry = () => {
    adminApi.telemetry().then(setData).catch((err) => setError(err.userMessage));
  };

  useEffect(loadTelemetry, []);

  const handleGlobalNuke = async (payload) => {
    setNukeBusy(true);
    try {
      const result = await adminApi.nukeGlobal(payload);
      toast.success(result.message || "Documents deleted.");
      setNukeOpen(false);
      loadTelemetry();
    } catch (err) {
      toast.error(err.userMessage || "Could not complete the nuke.");
    } finally {
      setNukeBusy(false);
    }
  };

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <LoadingState message="Loading telemetry..." />;

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Admin Dashboard</h1>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mb-6">
        <StatCard icon={Users} label="Total Users" value={data.totalUsers} />
        <StatCard icon={FileStack} label="Total Documents" value={data.totalDocuments} />
        <StatCard icon={CheckCircle2} label="Processed" value={data.documentsByStatus.processed} tone="text-accent" />
        <StatCard icon={XCircle} label="Failed" value={data.documentsByStatus.failed} tone="text-danger" />
        <StatCard icon={AlertTriangle} label="Low Confidence" value={data.documentsWithLowConfidence} tone="text-warning" />
        <StatCard icon={Layers} label="Multi-page" value={data.multiPageDocuments} />
        <StatCard icon={Activity} label="Activity (24h)" value={data.recentActivityLast24Hours} />
        <StatCard icon={Activity} label="Activity (7d)" value={data.recentActivityLast7Days} />
      </div>

      <div className="bg-surface border border-border rounded-lg p-4 mb-6">
        <h2 className="text-sm font-semibold text-text-muted mb-2">OCR failure rate</h2>
        <p className="text-2xl font-semibold">{(data.ocrFailureRate * 100).toFixed(1)}%</p>
      </div>

      <div className="bg-danger/5 border border-danger rounded-lg p-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-danger mb-2">
          <AlertTriangle size={14} /> Danger zone
        </h2>
        <p className="text-xs text-text-muted mb-3">
          Bulk-delete documents across every user, by age or by a specific year/month. This
          cannot be undone.
        </p>
        <button
          onClick={() => setNukeOpen(true)}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded border border-danger bg-danger/10 text-danger font-semibold hover:bg-danger/20"
        >
          <AlertTriangle size={12} /> Global nuke
        </button>
      </div>

      <NukeDialog
        open={nukeOpen}
        title="Nuke documents across ALL users?"
        description="This bulk-deletes documents matching the range below, across every user account. This cannot be undone."
        confirmationPhrase={NUKE_GLOBAL_PHRASE}
        confirmLabel="Nuke all users' documents"
        busy={nukeBusy}
        onConfirm={handleGlobalNuke}
        onCancel={() => setNukeOpen(false)}
      />
    </div>
  );
}
