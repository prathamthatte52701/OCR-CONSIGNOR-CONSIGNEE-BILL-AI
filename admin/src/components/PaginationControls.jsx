export default function PaginationControls({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-between mt-4 text-sm">
      <button
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        className="px-3 py-1.5 rounded border border-border disabled:opacity-30"
      >
        Previous
      </button>
      <span className="text-text-muted">
        Page {page} of {totalPages}
      </span>
      <button
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        className="px-3 py-1.5 rounded border border-border disabled:opacity-30"
      >
        Next
      </button>
    </div>
  );
}
