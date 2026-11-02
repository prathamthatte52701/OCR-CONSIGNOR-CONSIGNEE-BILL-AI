import { useRef, useState } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { useUploadDocument } from "../hooks/useDocumentMutations";
import UploadCard from "../components/UploadCard";
import BulkUpload from "../components/BulkUpload";

export default function UploadPage() {
  const [part1, setPart1] = useState(null);
  const [part2, setPart2] = useState(null);
  const [mode, setMode] = useState("single"); // "single" | "bulk"
  const upload = useUploadDocument();
  const submitting = useRef(false); // isPending lags one render behind a fast double click

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!part1 || !part2 || upload.isPending || submitting.current) return;
    submitting.current = true;
    upload.mutate({ part1, part2 }, { onSettled: () => (submitting.current = false) });
  };

  return (
    <div className={mode === "bulk" ? "max-w-4xl" : "max-w-2xl"}>
      <div className="flex gap-2 mb-4" role="tablist">
        {[
          ["single", "Single"],
          ["bulk", "Bulk (up to 5 sets)"],
        ].map(([value, text]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            onClick={() => setMode(value)}
            className={`rounded px-4 py-1.5 text-sm border ${
              mode === value ? "border-accent text-accent bg-accent/10" : "border-border text-text-muted"
            }`}
          >
            {text}
          </button>
        ))}
      </div>
      {mode === "bulk" ? (
        <BulkUpload />
      ) : (
        <>
      <h1 className="text-xl font-semibold mb-1">Upload document</h1>
      <p className="text-sm text-text-muted mb-6">
        Upload Part 1 (consignee/consignor header) and Part 2 (line-items table) together for one
        document record.
      </p>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid sm:grid-cols-2 gap-4">
          <UploadCard
            label="Part 1"
            hint="Header page - JPG, PNG or PDF, max 5 MB"
            file={part1}
            onFileSelect={setPart1}
            disabled={upload.isPending}
          />
          <UploadCard
            label="Part 2"
            hint="Line-items table - JPG, PNG or PDF, max 5 MB"
            file={part2}
            onFileSelect={setPart2}
            disabled={upload.isPending}
          />
        </div>

        <button
          type="submit"
          disabled={!part1 || !part2 || upload.isPending}
          className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-accent text-bg font-medium rounded px-6 py-2.5 text-sm hover:bg-accent-dim disabled:opacity-40"
        >
          {upload.isPending && <Loader2 className="animate-spin" size={16} />}
          {upload.isPending ? "Uploading..." : "Upload document"}
        </button>

        {upload.error && (
          <div role="alert" className="flex items-center gap-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
            <AlertCircle size={16} className="shrink-0" />
            {upload.error.userMessage || "Upload failed."}
          </div>
        )}
      </form>
        </>
      )}
    </div>
  );
}
