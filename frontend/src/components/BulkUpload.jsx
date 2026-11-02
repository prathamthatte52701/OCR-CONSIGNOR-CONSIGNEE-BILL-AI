import { useEffect, useRef, useState } from "react";
import { Loader2, AlertCircle, Plus, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { documentsApi } from "../api/documents";
import { useDocument } from "../hooks/useDocumentsQueries";
import { DocumentDetail } from "../pages/DocumentDetailPage";
import UploadCard from "./UploadCard";

const MAX_SETS = 5;
let nextKey = 1;
const newRow = () => ({ key: nextKey++, part1: null, part2: null, id: null, error: "" });

const STATUS_STYLE = {
  waiting: "text-text-muted",
  reading: "text-warning",
  done: "text-accent",
  failed: "text-danger",
};

function toStatus(uploadStatus) {
  if (uploadStatus === "processed") return "done";
  if (uploadStatus === "failed") return "failed";
  return "busy";
}

// One created set: polls its document (useDocument already refetches every 3 s while busy).
function SetRow({ n, id, isReading, onStatus }) {
  const { data } = useDocument(id);
  const status = data ? toStatus(data.uploadStatus) : "busy";
  useEffect(() => onStatus(id, status), [id, status, onStatus]);
  const label = status === "busy" ? (isReading ? "reading" : "waiting") : status;
  return (
    <li className="flex items-center justify-between rounded border border-border px-3 py-2 text-sm">
      <span>Set {n}</span>
      <span className={STATUS_STYLE[label]}>{label}</span>
    </li>
  );
}

export default function BulkUpload() {
  const [rows, setRows] = useState([newRow()]);
  const [uploading, setUploading] = useState(false);
  const [formError, setFormError] = useState("");
  const [statuses, setStatuses] = useState({}); // docId -> busy | done | failed
  const [page, setPage] = useState(0);
  const busyRef = useRef(false); // a fast double click can beat the `uploading` state

  const update = (key, patch) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const onStatus = (id, status) => setStatuses((s) => (s[id] === status ? s : { ...s, [id]: status }));

  const created = rows.filter((r) => r.id);
  const editable = rows.filter((r) => !r.id);
  const fresh = editable.filter((r) => !r.error);
  const failedRows = editable.filter((r) => r.error);
  const complete = (r) => r.part1 && r.part2;
  const canUploadAll = fresh.length > 0 && editable.every(complete) && !failedRows.length;
  const canRetry = failedRows.length > 0 && editable.every(complete);
  const reviewed = rows.filter((r) => r.id || r.error);
  const firstBusy = created.find((r) => (statuses[r.id] ?? "busy") === "busy")?.id;
  const doneCount = created.filter((r) => ["done", "failed"].includes(statuses[r.id])).length;
  const safePage = Math.min(page, Math.max(reviewed.length - 1, 0));

  async function send(batch) {
    if (busyRef.current) return;
    busyRef.current = true;
    setUploading(true);
    setFormError("");
    try {
      const { results } = await documentsApi.bulkUpload(batch.map((r) => ({ part1: r.part1, part2: r.part2 })));
      setRows((rs) =>
        rs.map((r) => {
          const i = batch.findIndex((b) => b.key === r.key);
          if (i < 0) return r;
          const res = results[i];
          return res?.id ? { ...r, id: res.id, error: "" } : { ...r, error: res?.error || "Upload failed." };
        })
      );
    } catch (err) {
      setFormError(err.userMessage || "Upload failed.");
    } finally {
      busyRef.current = false;
      setUploading(false);
    }
  }

  function reset() {
    setRows([newRow()]);
    setStatuses({});
    setPage(0);
    setFormError("");
  }

  const current = reviewed[safePage];

  return (
    <div className="space-y-6">
      {editable.length > 0 && (
        <div className="space-y-4">
          {editable.map((row) => {
            const n = rows.indexOf(row) + 1;
            const missing = (row.part1 && !row.part2 && "Part 2") || (!row.part1 && row.part2 && "Part 1");
            return (
              <div key={row.key} className="rounded-lg border border-border p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Set {n}</span>
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() => setRows((rs) => rs.filter((r) => r.key !== row.key))}
                    className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-danger disabled:opacity-40"
                  >
                    <Trash2 size={13} /> Remove
                  </button>
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  <UploadCard
                    label="Part 1"
                    hint="Header page - JPG, PNG or PDF, max 5 MB"
                    file={row.part1}
                    onFileSelect={(f) => update(row.key, { part1: f, error: "" })}
                    disabled={uploading}
                  />
                  <UploadCard
                    label="Part 2"
                    hint="Line-items table - JPG, PNG or PDF, max 5 MB"
                    file={row.part2}
                    onFileSelect={(f) => update(row.key, { part2: f, error: "" })}
                    disabled={uploading}
                  />
                </div>
                {missing && <p className="text-xs text-danger">{missing} missing</p>}
                {row.error && <p className="text-xs text-danger">{row.error}</p>}
              </div>
            );
          })}

          <div className="flex flex-wrap gap-3">
            {rows.length < MAX_SETS && (
              <button
                type="button"
                disabled={uploading}
                onClick={() => setRows((rs) => [...rs, newRow()])}
                className="inline-flex items-center gap-1.5 rounded border border-border px-4 py-2 text-sm hover:bg-surface-raised disabled:opacity-40"
              >
                <Plus size={14} /> Add set
              </button>
            )}
            <button
              type="button"
              disabled={!canUploadAll || uploading}
              onClick={() => send(fresh)}
              className="inline-flex items-center gap-2 bg-accent text-bg font-medium rounded px-6 py-2 text-sm hover:bg-accent-dim disabled:opacity-40"
            >
              {uploading && <Loader2 className="animate-spin" size={16} />}
              {uploading ? "Uploading..." : `Upload all (${fresh.length})`}
            </button>
            {failedRows.length > 0 && (
              <button
                type="button"
                disabled={!canRetry || uploading}
                onClick={() => send(failedRows)}
                className="rounded border border-accent px-4 py-2 text-sm text-accent hover:bg-accent/10 disabled:opacity-40"
              >
                Retry failed sets
              </button>
            )}
          </div>
        </div>
      )}

      {formError && (
        <div role="alert" className="flex items-center gap-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
          <AlertCircle size={16} className="shrink-0" />
          {formError}
        </div>
      )}

      {created.length > 0 && (
        <section className="space-y-2">
          <p className="text-sm text-text-muted">
            {doneCount < created.length
              ? `Reading ${doneCount + 1} of ${created.length}`
              : `All ${created.length} read`}
          </p>
          <ul className="space-y-1.5">
            {created.map((r) => (
              <SetRow
                key={r.id}
                n={rows.indexOf(r) + 1}
                id={r.id}
                isReading={r.id === firstBusy}
                onStatus={onStatus}
              />
            ))}
          </ul>
        </section>
      )}

      {current && (
        <section className="space-y-4 rounded-lg border border-border p-4">
          <div className="flex items-center justify-between">
            <button
              type="button"
              disabled={safePage === 0}
              onClick={() => setPage(safePage - 1)}
              className="inline-flex items-center gap-1 text-sm disabled:opacity-40"
            >
              <ChevronLeft size={16} /> Previous
            </button>
            <span className="text-sm text-text-muted">
              {safePage + 1} of {reviewed.length}
            </span>
            <button
              type="button"
              disabled={safePage >= reviewed.length - 1}
              onClick={() => setPage(safePage + 1)}
              className="inline-flex items-center gap-1 text-sm disabled:opacity-40"
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
          {current.id ? (
            <DocumentDetail key={current.id} id={current.id} />
          ) : (
            <p className="text-sm text-danger">Failed: {current.error}</p>
          )}
        </section>
      )}

      {created.length > 0 && (
        <button
          type="button"
          disabled={uploading}
          onClick={reset}
          className="rounded border border-border px-4 py-2 text-sm hover:bg-surface-raised disabled:opacity-40"
        >
          Start new batch
        </button>
      )}
    </div>
  );
}
