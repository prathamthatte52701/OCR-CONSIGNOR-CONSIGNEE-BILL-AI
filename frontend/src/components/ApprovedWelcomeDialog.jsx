import { useEffect, useRef } from "react";
import { useAuthStore } from "../store/authStore";
import { formatIST } from "../lib/formatDate";

// Shown once, on the first login after an admin approved the account (the server sends
// justApproved: true exactly once). OK and Esc both clear the flag for good.
export default function ApprovedWelcomeDialog() {
  const justApproved = useAuthStore((s) => s.justApproved);
  const approvedAt = useAuthStore((s) => s.approvedAt);
  const clear = useAuthStore((s) => s.clearJustApproved);
  const ref = useRef(null);

  useEffect(() => {
    if (justApproved) ref.current?.showModal();
  }, [justApproved]);

  if (!justApproved) return null;
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        clear();
      }}
      className="backdrop:bg-black/60 bg-surface text-text rounded-lg p-0 w-[92vw] max-w-sm ring-2 ring-border"
    >
      <div className="p-5">
        <h2 className="text-lg font-semibold mb-2">Your account was approved</h2>
        <p className="text-sm text-text-muted">
          The admin approved your account. You can now upload and manage documents.
        </p>
        {approvedAt && (
          <p className="mt-2 text-xs text-text-muted">Approved on {formatIST(approvedAt)}</p>
        )}
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            autoFocus
            onClick={clear}
            className="px-4 py-2 rounded text-sm font-medium bg-accent text-bg hover:bg-accent-dim"
          >
            OK
          </button>
        </div>
      </div>
    </dialog>
  );
}
