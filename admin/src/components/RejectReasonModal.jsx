import { useEffect, useRef, useState } from "react";

const CHIPS = ["Not an employee", "Duplicate account", "Wrong email", "Other"];
const MAX = 300;

// Reject (pending user) / Revoke (approved user) with an optional reason that the user sees
// when they try to log in. Plain text; onConfirm gets the trimmed reason or null.
export default function RejectReasonModal({ open, user, revoke, busy = false, onConfirm, onCancel }) {
  const ref = useRef(null);
  const [reason, setReason] = useState("");
  const verb = revoke ? "Revoke" : "Reject";

  useEffect(() => {
    if (open) {
      setReason("");
      ref.current?.showModal();
    } else {
      ref.current?.close();
    }
  }, [open]);

  if (!open || !user) return null;
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onCancel();
      }}
      className="backdrop:bg-black/60 bg-surface text-text rounded-lg p-0 w-[92vw] max-w-md ring-2 ring-danger"
    >
      <form
        className="p-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (!busy) onConfirm(reason.trim() || null);
        }}
      >
        <h2 className="text-lg font-semibold mb-1">
          {verb} {user.username}?
        </h2>
        <p className="text-sm text-text-muted">
          Optional reason. The user sees it when they try to log in.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {CHIPS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => setReason(chip === "Other" ? "" : chip)}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                reason === chip ? "border-accent bg-accent/20" : "border-border text-text-muted hover:border-accent/50"
              }`}
            >
              {chip}
            </button>
          ))}
        </div>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value.slice(0, MAX))}
          maxLength={MAX}
          rows={3}
          aria-label="Reason"
          placeholder="Reason (optional)"
          className="mt-3 w-full rounded border border-border bg-bg px-3 py-2 text-sm"
        />
        <p className="mt-1 text-right text-xs text-text-muted">
          {reason.length}/{MAX}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            className="px-4 py-2 rounded text-sm border border-border hover:bg-surface-raised"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="px-4 py-2 rounded text-sm font-medium bg-danger text-white hover:brightness-90 disabled:opacity-40"
          >
            {busy ? "Working..." : `Confirm ${verb.toLowerCase()}`}
          </button>
        </div>
      </form>
    </dialog>
  );
}
