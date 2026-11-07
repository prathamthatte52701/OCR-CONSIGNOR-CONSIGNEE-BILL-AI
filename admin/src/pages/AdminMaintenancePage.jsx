import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import PurgeMonthsDialog from "../components/PurgeMonthsDialog";
import { formatBytes } from "../lib/formatBytes";
import { formatIST } from "../lib/formatDate";

const ACTION_LABELS = {
  admin_nuke_attempt: "Nuke / purge",
  document_deleted: "Document deleted",
  document_file_purged: "Files purged",
  orphaned_file_dismissed: "Orphan dismissed",
  orphaned_file_retry_succeeded: "Orphan retry ok",
  orphaned_file_retry_failed: "Orphan retry failed",
  user_deleted: "User deleted",
};

function describe(item) {
  const c = item.context || {};
  if (item.action !== "admin_nuke_attempt") return "";
  const where = c.scope === "global" ? "all users" : "one user";
  const what = c.purge === "months" ? `older than ${c.months} months` : "range";
  if (c.reason === "success") {
    return `${where}, ${what}: ${c.deletedCount ?? 0} deleted, ${formatBytes(c.bytes)}`;
  }
  return `${where}, ${what}: refused (${String(c.reason || "").replace(/_/g, " ")})`;
}

function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

function Stat({ label, value }) {
  return (
    <div className="bg-surface border border-border rounded-lg px-4 py-3">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}

export default function AdminMaintenancePage() {
  const [system, setSystem] = useState(null);
  const [feed, setFeed] = useState([]);
  const [error, setError] = useState("");
  const [purgeOpen, setPurgeOpen] = useState(false);

  const load = useCallback(() => {
    setError("");
    adminApi.system().then(setSystem).catch((err) => setError(err.userMessage || "Could not load."));
    adminApi
      .maintenanceActivity()
      .then((d) => setFeed(d.items))
      .catch((err) => toast.error(err.userMessage || "Could not load activity."));
  }, []);

  useEffect(load, [load]);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!system) return <LoadingState message="Loading maintenance..." />;

  return (
    <div className="max-w-3xl space-y-8">
      <h1 className="text-xl font-semibold">Maintenance</h1>

      <section>
        <h2 className="text-sm font-semibold text-text-muted mb-3">Storage and health</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <Stat label="Stored files" value={system.storage.files} />
          <Stat label="Storage used" value={formatBytes(system.storage.bytes)} />
          <Stat label="Documents processed" value={`${system.documentsProcessed} / ${system.documentsTotal}`} />
          <Stat
            label="Database"
            value={system.db.ok ? `OK, ${system.db.pingMs} ms` : "Not responding"}
          />
          <Stat label="Server uptime" value={formatUptime(system.uptimeSeconds)} />
          <Stat label="Orphaned files" value={system.orphanedFiles} />
        </div>
        <div className="mt-3 flex gap-4 text-sm">
          <Link to="/orphaned-files" className="text-accent hover:underline">Orphaned files</Link>
          <Link to="/documents" className="text-accent hover:underline">Documents</Link>
          <Link to="/logs" className="text-accent hover:underline">Logs</Link>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-text-muted mb-3">Maintenance activity</h2>
        {feed.length === 0 ? (
          <p className="text-sm text-text-muted">Nothing yet.</p>
        ) : (
          <ul className="space-y-1">
            {feed.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap justify-between gap-2 bg-surface border border-border rounded px-3 py-2 text-sm"
              >
                <span>
                  <span className="font-medium">{ACTION_LABELS[item.action] || item.action}</span>
                  {describe(item) && <span className="text-text-muted"> - {describe(item)}</span>}
                  {item.by && <span className="text-text-muted"> (by {item.by})</span>}
                </span>
                <span className="text-xs text-text-muted">{formatIST(item.createdAt)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-danger/50 p-4">
        <h2 className="text-sm font-semibold text-danger mb-1">Danger zone</h2>
        <p className="text-xs text-text-muted mb-3">
          Deletes every user's documents older than 1, 2, 3, 6 or 9 months, with their files. Users,
          admins and the audit log are never touched.
        </p>
        <button
          type="button"
          onClick={() => setPurgeOpen(true)}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded border border-danger bg-danger/10 text-danger font-semibold hover:bg-danger/20"
        >
          <AlertTriangle size={12} /> Purge old documents (all users)
        </button>
      </section>

      <PurgeMonthsDialog
        open={purgeOpen}
        label="all users' documents"
        confirmationPhrase="NUKE ALL"
        onClose={() => setPurgeOpen(false)}
        onDone={() => {
          setPurgeOpen(false);
          load();
        }}
      />
    </div>
  );
}
