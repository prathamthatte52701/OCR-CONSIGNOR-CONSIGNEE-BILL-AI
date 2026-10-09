import { useEffect, useRef, useState } from "react";
import { cn } from "../lib/utils";

const SEVERITY_STYLES = {
  normal: { ring: "ring-border", button: "bg-accent text-bg hover:bg-accent-dim" },
  critical: { ring: "ring-danger", button: "bg-danger text-white hover:brightness-90" },
};


// Enter confirms, Escape cancels (Escape is the browser's native <dialog> "cancel" event).
// Enter is deliberately ignored when:
//  - focus is on a button/link/field - the control itself reacts (Cancel stays Cancel, and an
//    input inside a <form> still submits normally);
//  - the key is auto-repeating (holding Enter must never confirm the NEXT dialog as well);
//  - an IME is composing text, or the dialog is busy.
function isPlainEnter(event) {
  if (event.key !== "Enter" || event.repeat || event.isComposing) return false;
  return !["BUTTON", "A", "INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName);
}

export default function ConfirmModal({ open, title, message, severity = "normal", confirmLabel = "Confirm", requirePhrase, busy = false, onConfirm, onCancel }) {
  const ref = useRef(null);
  const confirmedRef = useRef(false); // a second Enter/click must never confirm twice
  const [phrase, setPhrase] = useState("");

  useEffect(() => {
    if (open) {
      confirmedRef.current = false;
      setPhrase("");
      ref.current?.showModal();
      // showModal() focuses the first button (Cancel), where Enter would cancel. Focus the
      // dialog itself instead so a plain Enter confirms; a typed-phrase modal keeps its input.
      if (!requirePhrase) ref.current?.focus();
    } else {
      ref.current?.close();
    }
  }, [open, requirePhrase]);

  if (!open) return null;
  const styles = SEVERITY_STYLES[severity] || SEVERITY_STYLES.normal;
  const phraseOk = !requirePhrase || phrase === requirePhrase;

  const confirm = () => {
    if (confirmedRef.current || busy || !phraseOk) return;
    confirmedRef.current = true;
    onConfirm();
  };

  return (
    <dialog
      ref={ref}
      tabIndex={-1}
      onKeyDown={(e) => {
        if (isPlainEnter(e)) {
          e.preventDefault();
          confirm();
        }
      }}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className={cn("backdrop:bg-black/60 bg-surface text-text rounded-lg p-0 w-[92vw] max-w-md ring-2 outline-none", styles.ring)}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          confirm();
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
            disabled={!phraseOk || busy}
            className={cn("px-4 py-2 rounded text-sm font-medium disabled:opacity-40", styles.button)}
          >
            {confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
