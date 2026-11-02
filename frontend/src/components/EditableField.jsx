import { useRef, useState } from "react";
import { Sparkles, TriangleAlert } from "lucide-react";
import { cn } from "../lib/utils";

function confidenceTone(confidence) {
  if (confidence >= 80) return "text-accent";
  if (confidence >= 40) return "text-warning";
  return "text-danger";
}

export default function EditableField({ label, value, confidence, autoCorrected, disabled, onSave }) {
  const [draft, setDraft] = useState(value ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  // A ref, not just state: two Enters (or Enter + click) in the same tick both see the stale
  // `saving === false` from the render closure and would each send a request.
  const savingRef = useRef(false);
  const dirty = draft !== (value ?? "");
  // A value that was read but is not trusted (editing sets confidence to 100, which clears this).
  const hasValue = value !== null && value !== undefined && value !== "";
  const lowConfidence = hasValue && typeof confidence === "number" && confidence < 80;
  const isCell = !label; // table cells stay tidy: outline + tooltip instead of a text line

  const handleSave = async () => {
    if (!dirty || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setError("");
    try {
      await onSave(draft === "" ? null : draft);
    } catch (err) {
      // The field stays open with what the user typed; show why the server refused it.
      setError(err?.userMessage || "Could not save.");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs text-text-muted">{label}</label>
        <div className="flex items-center gap-1.5">
          {autoCorrected && (
            <span title="Auto-corrected by the OCR pipeline" className="text-accent">
              <Sparkles size={12} />
            </span>
          )}
          {typeof confidence === "number" && (
            <span title="Confidence" className={cn("text-[10px] font-mono", confidenceTone(confidence))}>
              {confidence}%
            </span>
          )}
          {value === null || value === undefined || value === "" ? (
            <span title="Not extracted - needs manual entry" className="text-warning">
              <TriangleAlert size={12} />
            </span>
          ) : null}
        </div>
      </div>
      <div className="flex gap-1.5">
        <input
          value={draft}
          disabled={disabled}
          onChange={(e) => {
            setDraft(e.target.value);
            setError("");
          }}
          onKeyDown={(e) => {
            // not while an IME is composing text, and not for an auto-repeating held key
            if (e.key === "Enter" && !e.nativeEvent.isComposing && !e.repeat) handleSave();
          }}
          placeholder="Not extracted"
          title={lowConfidence && isCell ? "Check against the original" : undefined}
          className={cn(
            "w-full rounded border bg-bg px-2.5 py-1.5 text-sm disabled:opacity-50",
            dirty ? "border-accent" : lowConfidence && isCell ? "border-warning" : "border-border"
          )}
        />
        {dirty && (
          <button
            onClick={handleSave}
            disabled={saving || disabled}
            className="px-2.5 rounded bg-accent text-bg text-xs font-medium shrink-0 disabled:opacity-50"
          >
            {saving ? "..." : "Save"}
          </button>
        )}
      </div>
      {lowConfidence && !isCell && (
        <p className="mt-1 text-[11px] text-warning">Check against the original</p>
      )}
      {error && (
        <p role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
