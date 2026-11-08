import { useEffect, useRef, useState } from 'react'
import { clearAllChats } from '../../api/chat'
import PasswordInput from '../PasswordInput'
import { describeGlobalClearError, filesPart, isTyped } from '../../utils/chatAdminCore'

// Delete ALL chat messages (and chat files). Step 1: the admin password and a dry-run count (the
// server checks the password and counts; nothing is deleted). Step 2: the count is shown, type
// DELETE and confirm. A wrong password keeps the dialog open with the server's message. No <form>,
// so Enter can never trigger the delete. The password lives in state only while the dialog is open.
export default function GlobalChatDeleteDialog({ onClose, onDeleted }) {
  const ref = useRef(null)
  const [password, setPassword] = useState('')
  const [typed, setTyped] = useState('')
  const [counted, setCounted] = useState(null) // { messages, files, bytes }
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const dialog = ref.current
    const opener = document.activeElement
    dialog?.showModal()
    return () => {
      dialog?.close()
      opener?.focus?.()
    }
  }, [])

  async function count() {
    if (!password || busy) return
    setBusy(true)
    setError('')
    try {
      const res = await clearAllChats(password, true)
      setCounted({ messages: res.count, files: res.files ?? 0, bytes: res.bytes ?? 0 })
    } catch (err) {
      setError(describeGlobalClearError(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!counted || !isTyped(typed) || busy) return
    setBusy(true)
    setError('')
    try {
      const res = await clearAllChats(password, false)
      setPassword('')
      onDeleted({ messages: res.deleted, files: res.files ?? 0, bytes: res.bytes ?? 0 })
    } catch (err) {
      setError(describeGlobalClearError(err))
      setBusy(false)
    }
  }

  const close = () => {
    if (!busy) onClose()
  }

  return (
    <dialog
      ref={ref}
      aria-label="Delete all chat messages"
      onCancel={(e) => {
        e.preventDefault()
        close()
      }}
      className="w-[92vw] max-w-md rounded-lg bg-surface p-0 text-text ring-2 ring-danger backdrop:bg-black/60"
    >
      <div className="space-y-3 p-5">
        <h2 className="text-lg font-semibold text-danger">Delete ALL chat messages</h2>
        <p className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          This deletes every chat message, and every file sent in chat, between every user and every
          admin. It <span className="font-semibold">cannot be undone</span>. Documents are not touched.
        </p>

        <div>
          <label htmlFor="chat-delete-password" className="mb-1 block text-xs text-text-muted">Your password</label>
          <PasswordInput
            id="chat-delete-password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              setCounted(null)
              setTyped('')
            }}
            disabled={busy}
            autoComplete="current-password"
          />
        </div>

        {counted === null ? (
          <button
            type="button"
            onClick={count}
            disabled={!password || busy}
            className="rounded border border-border px-4 py-2 text-sm hover:bg-surface-raised disabled:opacity-40"
          >
            {busy ? 'Checking...' : 'Check password and count'}
          </button>
        ) : (
          <>
            <p role="status" className="text-sm font-medium text-warning">
              {counted.messages === 0
                ? 'There are no chat messages to delete.'
                : `${counted.messages} ${counted.messages === 1 ? 'message' : 'messages'}${filesPart(counted.files)} will be deleted.`}
            </p>
            <div>
              <label htmlFor="chat-delete-typed" className="mb-1 block text-xs text-text-muted">
                Type <span className="font-mono text-danger">DELETE</span> to confirm
              </label>
              <input
                id="chat-delete-typed"
                type="text"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                disabled={busy}
                autoComplete="off"
                placeholder="DELETE"
                className="w-full rounded border border-border bg-bg px-3 py-2 font-mono text-sm"
              />
            </div>
          </>
        )}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={close} disabled={busy} className="rounded border border-border px-4 py-2 text-sm hover:bg-surface-raised">
            Cancel
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={!counted || counted.messages === 0 || !isTyped(typed) || busy}
            className="rounded bg-danger px-4 py-2 text-sm font-medium text-white hover:brightness-90 disabled:opacity-40"
          >
            {busy && counted ? 'Deleting...' : 'Delete all chat messages'}
          </button>
        </div>
      </div>
    </dialog>
  )
}
