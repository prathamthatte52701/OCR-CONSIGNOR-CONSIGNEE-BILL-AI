import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { adminApi } from "../api/admin";
import ConfirmModal from "../components/ConfirmModal";
import LoadingState from "../components/LoadingState";
import { formatIST } from "../lib/formatDate";

// The temporary password lives only in this component's state, which unmounts with the dialog.
function TempPasswordModal({ request, onClose, onDone }) {
  const ref = useRef(null);
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    ref.current?.showModal();
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (busy || !password) return;
    setBusy(true);
    setError("");
    try {
      await adminApi.setTempPassword(request.id, password);
      setPassword("");
      onDone(`Temporary password set for ${request.username}. Tell them yourself - no email is sent.`);
    } catch (err) {
      setError(err.userMessage || "Could not set the password.");
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      className="backdrop:bg-black/60 bg-surface text-text rounded-lg p-0 w-[92vw] max-w-md ring-2 ring-border"
    >
      <form onSubmit={submit} autoComplete="off" className="p-5">
        <h2 className="text-lg font-semibold mb-1">Set temporary password</h2>
        <p className="text-sm text-text-muted">
          For {request.username} ({request.email}). They must choose a new password at their next
          login.
        </p>
        <p className="mt-3 rounded border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
          Tell the user the password yourself - no email is sent. Check who they are first.
        </p>
        <label className="mt-4 block text-xs text-text-muted mb-1" htmlFor="temp-pw">
          Temporary password
        </label>
        <input
          id="temp-pw"
          type={shown ? "text" : "password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="off"
          spellCheck={false}
          maxLength={64}
          className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={() => setShown((v) => !v)}
          className="mt-2 rounded border border-border px-2 py-0.5 text-xs hover:border-accent/50"
        >
          {shown ? "Hide" : "Show"}
        </button>
        <p className="mt-2 text-xs text-text-muted">
          8-64 characters with uppercase, lowercase, a number and a special character, no spaces.
        </p>
        {error && (
          <p role="alert" className="mt-3 rounded border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            className="px-4 py-2 rounded text-sm border border-border hover:bg-surface-raised"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || !password}
            className="px-4 py-2 rounded text-sm font-medium bg-accent text-bg hover:bg-accent-dim disabled:opacity-40"
          >
            {busy ? "Saving..." : "Set password"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

export default function PasswordRequestsPage() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [setting, setSetting] = useState(null);
  const [dismissing, setDismissing] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const data = await adminApi.passwordRequests({ status: showAll ? "all" : "open" });
      setRequests(data.requests || []);
    } catch (err) {
      setLoadError(err.userMessage || "Could not load password requests.");
    } finally {
      setLoading(false);
    }
  }, [showAll]);

  useEffect(() => {
    load();
  }, [load]);

  const afterChange = (message) => {
    setSetting(null);
    setDismissing(null);
    toast.success(message);
    load();
  };

  const dismiss = async () => {
    const r = dismissing;
    setBusy(true);
    try {
      await adminApi.dismissPasswordRequest(r.id);
      afterChange(`Request from ${r.username} dismissed.`);
    } catch (err) {
      setDismissing(null);
      toast.error(err.userMessage || "Could not dismiss the request.");
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Password requests</h1>
        <label className="flex items-center gap-2 text-sm text-text-muted">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
          Show resolved too
        </label>
      </div>
      <p className="text-xs text-text-muted mb-4">
        Users who asked for a password reset. Set a temporary password and tell them yourself - no
        email is sent. They must choose a new password at their next login.
      </p>

      {loading && requests.length === 0 ? (
        <LoadingState message="Loading requests..." />
      ) : loadError ? (
        <div className="text-center py-10">
          <p className="text-sm text-danger mb-3">{loadError}</p>
          <button
            type="button"
            onClick={load}
            className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:border-accent/50"
          >
            Retry
          </button>
        </div>
      ) : requests.length === 0 ? (
        <p className="text-sm text-text-muted py-10 text-center">
          {showAll ? "No password requests yet." : "No open password requests."}
        </p>
      ) : (
        <div className="space-y-2">
          {requests.map((r) => (
            <div
              key={r.id}
              className="flex flex-wrap items-center justify-between gap-3 bg-surface border border-border rounded-lg px-4 py-3"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">{r.username}</p>
                <p className="text-xs text-text-muted">{r.email}</p>
                {r.note && (
                  <p className="mt-1 text-xs text-text-muted whitespace-pre-wrap break-words">
                    Note: {r.note}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs text-text-muted">
                <span>{formatIST(r.updatedAt || r.createdAt)}</span>
                {r.status === "open" ? (
                  <>
                    <button
                      type="button"
                      onClick={() => setSetting(r)}
                      className="rounded px-2.5 py-1 text-bg bg-accent hover:bg-accent-dim"
                    >
                      Set temporary password
                    </button>
                    <button
                      type="button"
                      onClick={() => setDismissing(r)}
                      className="rounded border border-border px-2.5 py-1 hover:border-accent/50"
                    >
                      Dismiss
                    </button>
                  </>
                ) : (
                  <span>{(r.resolution || r.status).replace(/_/g, " ")}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {setting && (
        <TempPasswordModal
          key={setting.id}
          request={setting}
          onClose={() => setSetting(null)}
          onDone={afterChange}
        />
      )}
      <ConfirmModal
        open={Boolean(dismissing)}
        title="Dismiss request?"
        message={`Dismiss the password request from ${dismissing?.username}? Their password stays unchanged.`}
        confirmLabel="Dismiss"
        busy={busy}
        onConfirm={dismiss}
        onCancel={() => setDismissing(null)}
      />
    </div>
  );
}
