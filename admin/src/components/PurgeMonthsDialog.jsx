import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { adminApi } from "../api/admin";
import { formatBytes } from "../lib/formatBytes";

const MONTH_CHOICES = [1, 2, 3, 6, 9];

// Age-based purge: pick the age, see the dry-run count, then confirm with the same gate as the
// nukes (password twice + typed phrase). No <form>: the confirm button is type="button", so Enter
// can never trigger the delete. Pass userId for the per-user purge, omit it for the global one.
export default function PurgeMonthsDialog({ open, userId, label, confirmationPhrase, onClose, onDone }) {
  const ref = useRef(null);
  const [months, setMonths] = useState(MONTH_CHOICES[0]);
  const [preview, setPreview] = useState(null);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setMonths(MONTH_CHOICES[0]);
      setPassword("");
      setConfirmPassword("");
      setPhrase("");
      ref.current?.showModal();
    } else {
      ref.current?.close();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    let current = true;
    setPreview(null);
    adminApi
      .purgePreview(months, userId)
      .then((data) => current && setPreview(data))
      .catch((err) => current && toast.error(err.userMessage || "Could not count documents."));
    return () => {
      current = false;
    };
  }, [open, months, userId]);

  if (!open) return null;

  const canSubmit =
    phrase === confirmationPhrase &&
    password.length > 0 &&
    password === confirmPassword &&
    preview !== null &&
    preview.documents > 0 &&
    !busy;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    try {
      const data = await adminApi.purgeMonths(
        months,
        { password, confirmPassword, confirmationPhrase: phrase },
        userId
      );
      toast.success(data.message || "Documents deleted.");
      onDone(data);
    } catch (err) {
      toast.error(err.userMessage || "Could not purge.");
    } finally {
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
      className="backdrop:bg-black/60 bg-surface text-text rounded-lg p-0 w-[92vw] max-w-lg ring-2 ring-danger"
    >
      <div className="p-5 space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-danger">Purge old documents</h2>
          <p className="text-sm text-text-muted mt-1">
            Permanently deletes {label} older than the age below, with their stored files. Accounts
            and the audit log are kept. This cannot be undone.
          </p>
        </div>

        <div>
          <label className="text-xs text-text-muted block mb-1" htmlFor="purge-months">
            Older than
          </label>
          <select
            id="purge-months"
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
            className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
          >
            {MONTH_CHOICES.map((m) => (
              <option key={m} value={m}>
                {m} {m === 1 ? "month" : "months"}
              </option>
            ))}
          </select>
          <p role="status" className="mt-2 text-sm">
            {preview === null
              ? "Counting..."
              : `${preview.documents} document(s), about ${formatBytes(preview.bytes)} of files will be deleted.`}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted block mb-1">Your password</label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">Confirm password</label>
            <input
              type="password"
              autoComplete="current-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
            />
          </div>
          {confirmPassword.length > 0 && password !== confirmPassword && (
            <p className="col-span-2 text-xs text-danger">Passwords do not match.</p>
          )}
        </div>

        <div>
          <label className="text-xs text-text-muted block mb-1">
            Type <span className="font-mono text-danger">{confirmationPhrase}</span> to confirm
          </label>
          <input
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            className="w-full rounded border border-border bg-bg px-3 py-2 text-sm font-mono"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            className="px-4 py-2 rounded text-sm border border-border hover:bg-surface-raised"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            className="px-4 py-2 rounded text-sm font-medium bg-danger text-white hover:brightness-90 disabled:opacity-40"
          >
            {busy ? "Deleting..." : "Purge documents"}
          </button>
        </div>
      </div>
    </dialog>
  );
}
