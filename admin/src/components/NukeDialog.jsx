import { useEffect, useRef, useState } from "react";
import { cn } from "../lib/utils";

const AGE_OPTIONS = [3, 6, 9];
const YEAR_MONTH_RE = /^\d{4}-\d{2}$/;

// Double-password + typed-phrase + age-or-Year+Month bulk delete confirmation. Deliberately
// has no <form>/onSubmit anywhere - the confirm button is type="button" with a plain onClick
// only, so Enter can never trigger it (Feature 6's global Enter-to-confirm explicitly excludes
// this dialog; Esc still cancels normally via the native <dialog> onCancel event below).
export default function NukeDialog({
  open,
  title,
  description,
  confirmationPhrase,
  confirmLabel = "Nuke",
  busy = false,
  onConfirm,
  onCancel,
}) {
  const ref = useRef(null);
  const [mode, setMode] = useState("age");
  const [olderThanMonths, setOlderThanMonths] = useState(AGE_OPTIONS[0]);
  const [yearMonth, setYearMonth] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [phrase, setPhrase] = useState("");

  useEffect(() => {
    if (open) {
      setMode("age");
      setOlderThanMonths(AGE_OPTIONS[0]);
      setYearMonth("");
      setPassword("");
      setConfirmPassword("");
      setPhrase("");
      ref.current?.showModal();
    } else {
      ref.current?.close();
    }
  }, [open]);

  if (!open) return null;

  const phraseOk = phrase === confirmationPhrase;
  const passwordsFilled = password.length > 0 && confirmPassword.length > 0;
  const passwordsMatch = password === confirmPassword;
  const rangeOk = mode === "age" ? Boolean(olderThanMonths) : YEAR_MONTH_RE.test(yearMonth);
  const canSubmit = phraseOk && passwordsFilled && passwordsMatch && rangeOk && !busy;

  const handleConfirm = () => {
    if (!canSubmit) return;
    const [year, month] =
      mode === "month" ? yearMonth.split("-").map(Number) : [undefined, undefined];
    onConfirm({
      password,
      confirmPassword,
      confirmationPhrase: phrase,
      olderThanMonths: mode === "age" ? olderThanMonths : undefined,
      year: mode === "month" ? year : undefined,
      month: mode === "month" ? month : undefined,
    });
  };

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className="backdrop:bg-black/60 bg-surface text-text rounded-lg p-0 w-[92vw] max-w-lg ring-2 ring-danger"
    >
      <div className="p-5 space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-danger">{title}</h2>
          {description && (
            <p className="text-sm text-text-muted whitespace-pre-line mt-1">{description}</p>
          )}
        </div>

        <div>
          <label className="text-xs text-text-muted block mb-1">Delete documents</label>
          <div className="flex gap-2 mb-2">
            <button
              type="button"
              onClick={() => setMode("age")}
              className={cn(
                "text-xs px-3 py-1.5 rounded border",
                mode === "age"
                  ? "border-danger text-danger bg-danger/10"
                  : "border-border text-text-muted hover:bg-surface-raised"
              )}
            >
              Older than
            </button>
            <button
              type="button"
              onClick={() => setMode("month")}
              className={cn(
                "text-xs px-3 py-1.5 rounded border",
                mode === "month"
                  ? "border-danger text-danger bg-danger/10"
                  : "border-border text-text-muted hover:bg-surface-raised"
              )}
            >
              Specific year + month
            </button>
          </div>
          {mode === "age" ? (
            <select
              value={olderThanMonths}
              onChange={(e) => setOlderThanMonths(Number(e.target.value))}
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
            >
              {AGE_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m} months
                </option>
              ))}
            </select>
          ) : (
            <input
              type="month"
              value={yearMonth}
              onChange={(e) => setYearMonth(e.target.value)}
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
            />
          )}
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
          {passwordsFilled && !passwordsMatch && (
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
            onClick={onCancel}
            className="px-4 py-2 rounded text-sm border border-border hover:bg-surface-raised"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!canSubmit}
            className="px-4 py-2 rounded text-sm font-medium bg-danger text-white hover:brightness-90 disabled:opacity-40"
          >
            {busy ? "Deleting..." : confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
