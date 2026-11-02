import { useRef, useState } from "react";
import { UploadCloud, FileImage, AlertCircle } from "lucide-react";
import { validateDocumentFile, formatSize } from "../utils/documentValidation";
import { cn } from "../lib/utils";

export default function UploadCard({ label, hint, file, onFileSelect, disabled }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");

  function handleFile(f) {
    const err = validateDocumentFile(f);
    setError(err || "");
    onFileSelect(err ? null : f);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && !disabled) handleFile(f);
  }

  function clear() {
    setError("");
    onFileSelect(null);
  }

  return (
    <div>
      <div
        data-testid={`slot-${label}`}
        data-drag={dragOver ? "true" : "false"}
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 transition-colors",
          disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
          dragOver ? "border-accent bg-accent/10" : file ? "border-accent bg-accent/5" : "border-border hover:border-accent/50"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          aria-label={label}
          accept=".jpg,.jpeg,.png,.pdf"
          className="hidden"
          disabled={disabled}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
            e.target.value = "";
          }}
        />
        {file ? <FileImage className="text-accent" size={28} /> : <UploadCloud className="text-text-muted" size={28} />}
        <span className="text-sm font-medium">{label}</span>
        {file ? (
          <>
            <span className="text-xs text-center break-all">{file.name}</span>
            <span className="text-xs text-text-muted">{formatSize(file.size)}</span>
            <div className="flex gap-3 text-xs">
              <button
                type="button"
                disabled={disabled}
                className="underline text-accent"
                onClick={(e) => {
                  e.stopPropagation();
                  inputRef.current?.click();
                }}
              >
                Replace
              </button>
              <button
                type="button"
                disabled={disabled}
                className="underline text-text-muted"
                onClick={(e) => {
                  e.stopPropagation();
                  clear();
                }}
              >
                Clear
              </button>
            </div>
          </>
        ) : (
          <span className="text-xs text-text-muted text-center">{hint}</span>
        )}
      </div>
      {error && (
        <div role="alert" className="mt-2 flex items-center gap-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          <AlertCircle size={14} className="shrink-0" />
          {error}
        </div>
      )}
    </div>
  );
}
