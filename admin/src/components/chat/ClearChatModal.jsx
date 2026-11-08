import { useEffect, useRef, useState } from 'react'
import { clearThread } from '../../api/chat'
import { CLEAR_RANGES, clearSummary, createTokens, filesPart, isTyped } from '../../utils/chatAdminCore'

// Deletes one user's chat by age. Every range change asks the server for a dry-run count first; the
// Delete button stays off until that count is in, is above zero and the word DELETE is typed.
// Native <dialog>: focus is trapped, Escape closes it (not while deleting) and focus goes back to
// the element that opened it. No <form>, so Enter can never trigger the delete.
export default function ClearChatModal({ user, onClose, onCleared }) {
  const ref = useRef(null)
  const [tokens] = useState(createTokens)
  const [range, setRange] = useState(null)
  const [count, setCount] = useState(null) // { range, n, files } | { range, failed: true }
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [deleted, setDeleted] = useState(null)

  useEffect(() => {
    const dialog = ref.current
    const opener = document.activeElement
    dialog?.showModal()
    return () => {
      dialog?.close()
      opener?.focus?.()
    }
  }, [])

  function pickRange(id) {
    setRange(id)
    setCount(null)
    setError('')
    const token = tokens.next()
    clearThread(user.userId, id, true).then(
      (res) => { if (tokens.isCurrent(token)) setCount({ range: id, n: res.count, files: res.files ?? 0 }) },
      () => { if (tokens.isCurrent(token)) setCount({ range: id, failed: true }) },
    )
  }

  const counted = count && count.range === range && !count.failed ? count.n : null
  const countedFiles = counted !== null ? count.files : 0
  const canDelete = counted > 0 && isTyped(typed) && !busy

  async function remove() {
    if (!canDelete) return
    setBusy(true)
    setError('')
    try {
      const res = await clearThread(user.userId, range, false)
      setDeleted({ messages: res.deleted, files: res.files ?? 0 })
      onCleared()
    } catch (err) {
      setError(err.userMessage || 'Could not delete the messages. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  function close() {
    if (!busy) onClose()
  }

  let status = ''
  if (range && counted !== null) status = clearSummary(range, counted, countedFiles)
  else if (range && count?.failed) status = 'Could not count the messages. Pick the range again.'
  else if (range) status = 'Counting messages...'

  return (
    <dialog
      ref={ref}
      aria-label={`Clear chat with ${user.name}`}
      onCancel={(e) => {
        e.preventDefault()
        close()
      }}
      className="w-[92vw] max-w-md rounded-lg bg-surface p-0 text-text ring-2 ring-danger backdrop:bg-black/60"
    >
      <div className="space-y-3 p-5">
        <h2 className="text-lg font-semibold text-danger">Clear chat with {user.name}</h2>
        {deleted !== null ? (
          <>
            <p role="status" className="text-sm text-accent">
              Deleted {deleted.messages} {deleted.messages === 1 ? 'message' : 'messages'}{filesPart(deleted.files)}.
            </p>
            <button type="button" onClick={onClose} className="rounded border border-border px-4 py-2 text-sm hover:bg-surface-raised">
              Close
            </button>
          </>
        ) : (
          <>
            <p className="text-sm text-text-muted">
              Only this user&apos;s chat is affected. Files sent in it are deleted too. This cannot be undone.
            </p>
            <div role="radiogroup" aria-label="Delete messages" className="grid gap-1.5">
              {CLEAR_RANGES.map((r) => (
                <label key={r.id} className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="clear-range"
                    className="h-4 w-4 accent-danger"
                    checked={range === r.id}
                    disabled={busy}
                    onChange={() => pickRange(r.id)}
                  />
                  {r.label}
                </label>
              ))}
            </div>
            <p role="status" aria-live="polite" className="min-h-5 text-sm font-medium text-warning">{status}</p>
            <div>
              <label htmlFor="clear-typed" className="mb-1 block text-xs text-text-muted">
                Type <span className="font-mono text-danger">DELETE</span> to confirm
              </label>
              <input
                id="clear-typed"
                type="text"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                disabled={busy}
                autoComplete="off"
                placeholder="DELETE"
                className="w-full rounded border border-border bg-bg px-3 py-2 font-mono text-sm"
              />
            </div>
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={close} disabled={busy} className="rounded border border-border px-4 py-2 text-sm hover:bg-surface-raised">
                Cancel
              </button>
              <button
                type="button"
                onClick={remove}
                disabled={!canDelete}
                className="rounded bg-danger px-4 py-2 text-sm font-medium text-white hover:brightness-90 disabled:opacity-40"
              >
                {busy ? 'Deleting...' : 'Delete messages'}
              </button>
            </div>
          </>
        )}
      </div>
    </dialog>
  )
}
