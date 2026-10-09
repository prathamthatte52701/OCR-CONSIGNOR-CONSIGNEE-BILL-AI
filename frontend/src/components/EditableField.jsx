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
  // A ref, not just state: two Enters (or Enter + click) in the same tick both see the stale
  // `saving === false` from the render closure and would each send a request.
  const savingRef = useRef(false);
  const dirty = draft !== (value ?? "");

  const handleSave = async () => {
    if (!dirty || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    try {
      await onSave(draft === "" ? null : draft);
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
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // not while an IME is composing text, and not for an auto-repeating held key
            if (e.key === "Enter" && !e.nativeEvent.isComposing && !e.repeat) handleSave();
          }}
          placeholder="Not extracted"
          className={cn(
            "w-full rounded border bg-bg px-2.5 py-1.5 text-sm disabled:opacity-50",
            dirty ? "border-accent" : "border-border"
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
    </div>
  );
}
