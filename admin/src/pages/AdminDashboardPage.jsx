import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  FileStack,
  KeyRound,
  Layers,
  RefreshCw,
  ScrollText,
  Users,
  Wrench,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import NukeDialog from "../components/NukeDialog";
import { AreaChart, Donut, Gauge, Sparkline } from "../components/charts";
import { PALETTE } from "../lib/palette";
import { notifyCountsChanged } from "../utils/events";
import {
  activityCategory,
  describeActivity,
  lastN,
  relativeTime,
  seriesOk,
  successRate,
  sum,
  trendText,
} from "../lib/dashboardCore";

const NUKE_GLOBAL_PHRASE = "NUKE ALL";
const fmt = (n) => n.toLocaleString("en-US");

function Card({ title, action, children, className = "" }) {
  return (
    <section aria-label={title} className={`bg-surface border border-border rounded-lg p-4 ${className}`}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Empty({ title, hint }) {
  return (
    <div className="px-4 py-8 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="mt-1 text-xs text-text-muted">{hint}</p>}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, tone = "text-text", trend, sparkline, sparkColor, to }) {
  const body = (
    <div className="h-full bg-surface border border-border rounded-lg p-4 hover:border-accent/50">
      <div className="flex items-center gap-2 text-text-muted text-xs mb-2">
        <Icon size={14} />
        {label}
      </div>
      <p className={`text-2xl font-semibold ${tone}`}>{value}</p>
      <p className="mt-1 min-h-4 text-xs text-text-muted">{trend}</p>
      <div className="mt-2 h-10">
        {sparkline && <Sparkline values={sparkline} color={sparkColor} width={200} height={40} className="w-full" />}
      </div>
    </div>
  );
  return to ? (
    <Link to={to} className="block h-full">
      {body}
    </Link>
  ) : (
    body
  );
}

function ActivityCard({ feed }) {
  return (
    <Card
      title="Recent activity"
      className="h-full"
      action={
        <Link to="/logs" className="text-xs text-accent hover:underline">
          View all
        </Link>
      }
    >
      {feed.length === 0 ? (
        <Empty title="Nothing has happened yet" hint="Sign-ins, approvals and uploads will show up here." />
      ) : (
        <ul className="divide-y divide-border">
          {feed.map((item) => (
            <li key={item.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm" title={describeActivity(item)}>
                  {describeActivity(item)}
                </p>
                <time className="text-xs text-text-muted" dateTime={item.createdAt}>
                  {relativeTime(item.createdAt)}
                </time>
              </div>
              <span className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[11px] text-text-muted">
                {activityCategory(item.action)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PendingCard({ pending, onApprove, busyId }) {
  const list = pending.oldest || [];
  return (
    <Card
      title={pending.count > 0 ? `Pending approvals (${pending.count})` : "Pending approvals"}
      action={
        <Link to="/users" className="text-xs text-accent hover:underline">
          Review
        </Link>
      }
    >
      {list.length === 0 ? (
        <Empty title="No pending requests" hint="New account requests will appear here." />
      ) : (
        <ul className="divide-y divide-border">
          {list.map((u) => (
            <li key={u.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium" title={u.username}>
                  {u.username}
                </p>
                <p className="truncate text-xs text-text-muted" title={u.email}>
                  {u.email} · {relativeTime(u.createdAt) || "recently"}
                </p>
              </div>
              <button
                type="button"
                disabled={busyId === u.id}
                onClick={() => onApprove(u)}
                aria-label={`Approve ${u.username}`}
                className="shrink-0 rounded border border-accent px-3 py-1 text-xs font-semibold text-accent hover:bg-accent/10 disabled:opacity-50"
              >
                {busyId === u.id ? "Approving..." : "Approve"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const ACTIONS = [
  { to: "/users", icon: Users, title: "Users", hint: "Manage user access" },
  { to: "/documents", icon: FileStack, title: "Documents", hint: "Browse documents" },
  { to: "/logs", icon: ScrollText, title: "Logs", hint: "Audit log" },
  { to: "/maintenance", icon: Wrench, title: "Maintenance", hint: "Storage and cleanup" },
  { to: "/password-requests", icon: KeyRound, title: "Password requests", hint: "Reset requests" },
];

function QuickActions({ openRequests }) {
  return (
    <nav aria-label="Quick actions" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {ACTIONS.map(({ to, icon: Icon, title, hint }) => (
        <Link
          key={to}
          to={to}
          className="flex items-center gap-3 bg-surface border border-border rounded-lg p-3 hover:border-accent/50"
        >
          <Icon size={18} className="shrink-0 text-accent" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{title}</span>
            <span className="block truncate text-xs text-text-muted">
              {to === "/password-requests" && openRequests > 0 ? `${openRequests} open` : hint}
            </span>
          </span>
          <ChevronRight size={16} className="shrink-0 text-text-muted" />
        </Link>
      ))}
    </nav>
  );
}

function Dashboard({ data, onApprove, busyId }) {
  const series = data.series || {};
  const days = series.days;
  const processed = data.documentsByStatus?.processed;
  const failed = data.documentsByStatus?.failed;
  const rate = successRate(processed, failed);
  const pending = data.pendingUsers || { count: 0, oldest: [] };
  const trends = data.trends || {};
  const feed = Array.isArray(data.activityFeed) ? data.activityFeed : [];
  const statusSegs = [
    { name: "Processed", color: PALETTE.accent, value: data.documentsByStatus?.processed || 0 },
    { name: "Failed", color: PALETTE.danger, value: data.documentsByStatus?.failed || 0 },
    { name: "Waiting", color: PALETTE.warning, value: (data.documentsByStatus?.uploaded || 0) + (data.documentsByStatus?.processing || 0) },
  ];
  const statusTotal = statusSegs.reduce((a, s) => a + s.value, 0);

  return (
    <div className="space-y-4">
      <section aria-label="Key numbers" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={Users} label="Total users" value={fmt(data.totalUsers)} to="/users"
          trend={trendText(trends.users?.current, trends.users?.previous)} />
        <StatCard icon={FileStack} label="Uploads (14 days)" value={fmt(sum(series.uploads))} to="/documents"
          trend={trendText(trends.uploads?.current, trends.uploads?.previous)}
          sparkline={lastN(series.uploads, SERIES_SPARK)} sparkColor={PALETTE.accent} />
        <StatCard icon={XCircle} label="Failed (14 days)" value={fmt(sum(series.failures))} tone="text-danger"
          trend={trendText(trends.failures?.current, trends.failures?.previous)}
          sparkline={lastN(series.failures, SERIES_SPARK)} sparkColor={PALETTE.danger} />
        <StatCard icon={CheckCircle2} label="OCR success rate" value={rate === null ? "-" : `${rate}%`} tone="text-accent"
          trend={rate === null ? "No finished documents yet" : `${fmt(processed)} of ${fmt(processed + failed)} finished`} />
      </section>

      <section aria-label="Charts" className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr_1fr]">
        <Card title="Uploads over time" className="lg:col-span-1">
          {seriesOk(days, series.uploads) ? (
            <>
              <p className="mb-2 text-xs text-text-muted">
                <span className="mr-2 text-2xl font-semibold text-text">{fmt(sum(series.uploads))}</span>
                in the last {days.length} days
              </p>
              <AreaChart days={days} values={series.uploads} label="Uploads per day" />
            </>
          ) : (
            <Empty title="No data yet" />
          )}
        </Card>

        <Card title="Document status">
          {statusTotal === 0 ? (
            <Empty title="No documents yet" hint="Statuses appear once users upload documents." />
          ) : (
            <div className="flex flex-col items-center gap-3">
              <Donut segments={statusSegs} total={fmt(statusTotal)} size={150} />
              <ul className="w-full space-y-1.5">
                {statusSegs.map((s) => (
                  <li key={s.name} className="flex items-center justify-between gap-3 text-sm">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: s.color }} />
                      <span className="truncate">{s.name}</span>
                    </span>
                    <span className="shrink-0 font-semibold">{fmt(s.value)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card title="OCR success rate">
          {rate === null ? (
            <Empty title="No finished documents yet" hint="Shown once a document has been processed or has failed." />
          ) : (
            <div className="flex flex-col items-center">
              <Gauge value={rate} label="Processed" width={200} />
              <p className="mt-2 text-center text-xs text-text-muted">
                {fmt(processed)} processed, {fmt(failed)} failed
              </p>
            </div>
          )}
        </Card>
      </section>

      <section aria-label="Activity and shortcuts" className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ActivityCard feed={feed} />
        <div className="flex flex-col gap-4">
          <PendingCard pending={pending} onApprove={onApprove} busyId={busyId} />
          <QuickActions openRequests={data.passwordRequests?.count || 0} />
        </div>
      </section>

      <section aria-label="More numbers" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={FileStack} label="Total documents" value={fmt(data.totalDocuments)} />
        <StatCard icon={AlertTriangle} label="Low confidence" value={fmt(data.documentsWithLowConfidence)} tone="text-warning" />
        <StatCard icon={Layers} label="Multi-page" value={fmt(data.multiPageDocuments)} />
        <StatCard icon={Activity} label="Activity (24h / 7d)" value={`${fmt(data.recentActivityLast24Hours)} / ${fmt(data.recentActivityLast7Days)}`} />
      </section>
    </div>
  );
}

const SERIES_SPARK = 14;

export default function AdminDashboardPage() {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [nukeOpen, setNukeOpen] = useState(false);
  const [nukeBusy, setNukeBusy] = useState(false);
  const approving = useRef(new Set()); // synchronous guard: a double click is ignored, not re-sent

  const load = useCallback(() => {
    return adminApi
      .telemetry()
      .then((d) => {
        setData(d);
        setLoadError("");
      })
      .catch((err) => setLoadError(err.userMessage || "Could not load the dashboard."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const retry = () => {
    setLoading(true);
    load();
  };

  async function approve(u) {
    if (approving.current.has(u.id)) return;
    approving.current.add(u.id);
    setBusyId(u.id);
    try {
      await adminApi.approveUser(u.id);
      toast.success(`${u.username} approved.`);
    } catch (err) {
      toast.error(err.userMessage || "Could not approve this user.");
    } finally {
      approving.current.delete(u.id);
      setBusyId(null);
      await load();
      notifyCountsChanged();
    }
  }

  const handleGlobalNuke = async (payload) => {
    setNukeBusy(true);
    try {
      const result = await adminApi.nukeGlobal(payload);
      toast.success(result.message || "Documents deleted.");
      setNukeOpen(false);
      load();
    } catch (err) {
      toast.error(err.userMessage || "Could not complete the nuke.");
    } finally {
      setNukeBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Admin Dashboard</h1>
        {data && (
          <button
            type="button"
            onClick={retry}
            aria-label="Refresh dashboard"
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text"
          >
            <RefreshCw size={12} /> Refresh
          </button>
        )}
      </div>

      {loading && !data ? (
        <LoadingState message="Loading dashboard..." />
      ) : data ? (
        <Dashboard data={data} onApprove={approve} busyId={busyId} />
      ) : (
        <div role="alert" className="bg-surface border border-border rounded-lg p-6 text-center">
          <p className="text-sm text-danger">{loadError || "Could not load the dashboard."}</p>
          <button
            type="button"
            onClick={retry}
            className="mt-3 rounded border border-border px-4 py-1.5 text-sm hover:bg-surface-raised"
          >
            Retry
          </button>
        </div>
      )}

      <div className="mt-6 bg-danger/5 border border-danger rounded-lg p-4">
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
