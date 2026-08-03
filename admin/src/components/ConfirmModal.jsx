import { useEffect, useRef, useState } from "react";
import { cn } from "../lib/utils";

const SEVERITY_STYLES = {
  normal: { ring: "ring-border", button: "bg-accent text-bg hover:bg-accent-dim" },
  critical: { ring: "ring-danger", button: "bg-danger text-white hover:brightness-90" },
};

export default function ConfirmModal({ open, title, message, severity = "normal", confirmLabel = "Confirm", requirePhrase, onConfirm, onCancel }) {
  const ref = useRef(null);
  const [phrase, setPhrase] = useState("");

  useEffect(() => {
    if (open) {
      setPhrase("");
      ref.current?.showModal();
    } else {
      ref.current?.close();
    }
  }, [open]);

  if (!open) return null;
  const styles = SEVERITY_STYLES[severity] || SEVERITY_STYLES.normal;
  const phraseOk = !requirePhrase || phrase === requirePhrase;

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className={cn("backdrop:bg-black/60 bg-surface text-text rounded-lg p-0 w-[92vw] max-w-md ring-2", styles.ring)}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (phraseOk) onConfirm();
        }}
        className="p-5"
      >
        <h2 className="text-lg font-semibold mb-2">{title}</h2>
        <p className="text-sm text-text-muted whitespace-pre-line">{message}</p>

        {requirePhrase && (
          <div className="mt-4">
            <label className="text-xs text-text-muted block mb-1">
              Type <span className="font-mono text-danger">{requirePhrase}</span> to confirm
            </label>
            <input
              autoFocus
              value={phrase}
              onChange={(e) => setPhrase(e.target.value)}
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm font-mono"
            />
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="px-4 py-2 rounded text-sm border border-border hover:bg-surface-raised">
            Cancel
          </button>
          <button
            type="submit"
            disabled={!phraseOk}
            className={cn("px-4 py-2 rounded text-sm font-medium disabled:opacity-40", styles.button)}
          >
            {confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
