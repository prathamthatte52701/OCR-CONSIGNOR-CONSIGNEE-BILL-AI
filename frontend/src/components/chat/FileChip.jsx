import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { fileKind, formatBytes } from '../../utils/chatCore'

// The chosen file above the text box: thumbnail (image) or PDF icon, name, size, remove button.
export default function FileChip({ file, disabled, onRemove }) {
  const isImage = fileKind(file) === 'image'
  const [thumb, setThumb] = useState(null)
  useEffect(() => {
    if (!isImage) return undefined
    const url = URL.createObjectURL(file)
    const show = setTimeout(() => setThumb(url), 0)
    return () => {
      clearTimeout(show)
      URL.revokeObjectURL(url)
    }
  }, [file, isImage])
  return (
    <div className="mx-4 flex items-center gap-2 rounded-xl border border-border bg-bg p-1.5">
      {isImage && thumb ? (
        <img src={thumb} alt="" className="h-10 w-10 shrink-0 rounded-md object-cover" />
      ) : (
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-surface-raised text-[10px] font-bold text-danger">PDF</span>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold text-text">{file.name}</p>
        <p className="text-[11px] text-text-muted">{formatBytes(file.size)}</p>
      </div>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label="Remove file"
        className="rounded-md p-1.5 text-text-muted hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  )
}
