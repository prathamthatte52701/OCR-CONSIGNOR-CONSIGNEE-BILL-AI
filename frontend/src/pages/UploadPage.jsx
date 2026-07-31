import { useState } from "react";
import { UploadCloud, FileImage } from "lucide-react";
import { useUploadDocument } from "../hooks/useDocumentMutations";
import { cn } from "../lib/utils";

function FileSlot({ label, hint, file, onChange }) {
  return (
    <label
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors",
        file ? "border-accent bg-accent/5" : "border-border hover:border-accent/50"
      )}
    >
      <input
        type="file"
        accept="image/jpeg,image/jpg,image/png,application/pdf"
        className="hidden"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      {file ? <FileImage className="text-accent" size={28} /> : <UploadCloud className="text-text-muted" size={28} />}
      <span className="text-sm font-medium">{label}</span>
      <span className="text-xs text-text-muted text-center">{file ? file.name : hint}</span>
    </label>
  );
}

export default function UploadPage() {
  const [part1, setPart1] = useState(null);
  const [part2, setPart2] = useState(null);
  const upload = useUploadDocument();

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!part1 || !part2) return;
    upload.mutate({ part1, part2 });
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold mb-1">Upload document</h1>
      <p className="text-sm text-text-muted mb-6">
        Upload Part 1 (consignee/consignor header) and Part 2 (line-items table) together for one
        document record.
      </p>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid sm:grid-cols-2 gap-4">
          <FileSlot
            label="Part 1"
            hint="Header page - image or PDF, max 5MB"
            file={part1}
            onChange={setPart1}
          />
          <FileSlot
            label="Part 2"
            hint="Line-items table - image or PDF, max 5MB"
            file={part2}
            onChange={setPart2}
          />
        </div>

        <button
          type="submit"
          disabled={!part1 || !part2 || upload.isPending}
          className="w-full sm:w-auto bg-accent text-bg font-medium rounded px-6 py-2.5 text-sm hover:bg-accent-dim disabled:opacity-40"
        >
          {upload.isPending ? "Uploading..." : "Upload document"}
        </button>
      </form>
    </div>
  );
}
