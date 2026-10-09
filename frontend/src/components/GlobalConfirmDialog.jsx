import { useEffect, useRef, useState } from "react";
import { useDialogStore } from "../store/dialogStore";
import { cn } from "../lib/utils";

const SEVERITY_STYLES = {
  normal: { ring: "ring-border", button: "bg-accent text-bg hover:bg-accent-dim" },
  warning: { ring: "ring-warning", button: "bg-warning text-bg hover:brightness-90" },
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

export default function GlobalConfirmDialog() {
  const dialog = useDialogStore((s) => s.dialog);
  const ref = useRef(null);
  const confirmedRef = useRef(false); // a second Enter/click must never confirm twice
  const [phraseInput, setPhraseInput] = useState("");

  useEffect(() => {
    if (dialog) {
      confirmedRef.current = false;
      setPhraseInput("");
      ref.current?.showModal();
      // showModal() focuses the first button (Cancel), where Enter would cancel. Focus the
      // dialog itself instead so a plain Enter confirms; a typed-phrase dialog keeps its input.
      if (!dialog.requirePhrase) ref.current?.focus();
    } else {
      ref.current?.close();
    }
  }, [dialog]);

  if (!dialog) return null;
  const styles = SEVERITY_STYLES[dialog.severity] || SEVERITY_STYLES.normal;
  const phraseOk = !dialog.requirePhrase || phraseInput === dialog.requirePhrase;

  const confirm = () => {
    if (confirmedRef.current || !phraseOk) return;
    confirmedRef.current = true;
    dialog.onConfirm();
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
        dialog.onCancel();
      }}
      className={cn(
        "backdrop:bg-black/60 bg-surface text-text rounded-lg p-0 w-[92vw] max-w-md ring-2 outline-none",
        styles.ring
      )}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          confirm();
        }}
        className="p-5"
      >
        <h2 className="text-lg font-semibold mb-2">{dialog.title}</h2>
        <p className="text-sm text-text-muted whitespace-pre-line">{dialog.message}</p>

        {dialog.requirePhrase && (
          <div className="mt-4">
            <label className="text-xs text-text-muted block mb-1">
              Type <span className="font-mono text-danger">{dialog.requirePhrase}</span> to confirm
            </label>
            <input
              autoFocus
              value={phraseInput}
              onChange={(e) => setPhraseInput(e.target.value)}
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm font-mono"
            />
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={dialog.onCancel}
            className="px-4 py-2 rounded text-sm border border-border hover:bg-surface-raised"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!phraseOk}
            className={cn("px-4 py-2 rounded text-sm font-medium disabled:opacity-40", styles.button)}
          >
            {dialog.confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
