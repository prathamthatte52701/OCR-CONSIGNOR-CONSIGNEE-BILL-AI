import { useRef } from 'react'
import { MAX_CHARS, canSend as canSendCore, countChars, isSubmitKey } from '../../utils/chatCore'
import FileChip from './FileChip'

const COUNTER_FROM = 800
const FOCUS = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent'

export default function Composer({
  userName, draft, onDraftChange, onSend, sending, error, disabled, file, onFileChange, fileError, progress,
}) {
  const inputRef = useRef(null)
  const trimmed = draft.trim()
  const chars = countChars(draft)
  const canSend = canSendCore({ text: draft, file }) && !sending && !disabled

  function submit() {
    if (canSend) onSend(trimmed)
  }

  function pick(e) {
    onFileChange(e.target.files?.[0] ?? null)
    e.target.value = '' // choosing the same file again must still fire
  }

  return (
    <div className="space-y-2 border-t border-border bg-surface px-4 pb-3 pt-3">
      {error && <p role="alert" className="text-xs text-danger">{error}</p>}
      {fileError && <p role="alert" className="text-xs text-danger">{fileError}</p>}
      {file && <FileChip file={file} disabled={sending} onRemove={() => onFileChange(null)} />}
      <textarea
        value={draft}
        rows={3}
        disabled={disabled}
        aria-label="Message"
        placeholder={file ? 'Add a caption (optional)' : userName ? `Reply to ${userName}` : 'Reply'}
        onChange={(e) => onDraftChange(e.target.value)}
        onKeyDown={(e) => {
          if (isSubmitKey(e)) {
            e.preventDefault()
            submit()
          }
        }}
        className={`block max-h-40 w-full resize-none rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted disabled:opacity-50 ${FOCUS}`}
      />
      <div className="flex items-center gap-2">
        <input ref={inputRef} type="file" hidden accept=".jpg,.jpeg,.png,.webp,.pdf" onChange={pick} />
        <button
          type="button"
          aria-label="Attach a file"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || sending}
          className={`rounded-lg border border-border p-1.5 text-text-muted hover:bg-surface-raised disabled:opacity-50 ${FOCUS}`}
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="m21 12-8.6 8.6a5 5 0 0 1-7-7L14 5a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4L15 8" /></svg>
        </button>
        <span className="flex-1" />
        {chars > COUNTER_FROM && (
          <span className={`text-xs tabular-nums ${chars >= MAX_CHARS ? 'text-danger' : 'text-text-muted'}`}>
            {chars}/{MAX_CHARS}
          </span>
        )}
        <button
          type="button"
          onClick={submit}
          disabled={!canSend}
          className={`flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-bg hover:bg-accent-dim disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS}`}
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="m22 2-7 20-4-9-9-4zM22 2 11 13" /></svg>
          {sending ? (file && progress > 0 && progress < 100 ? `Sending ${progress}%` : 'Sending...') : 'Send'}
        </button>
      </div>
    </div>
  )
}
