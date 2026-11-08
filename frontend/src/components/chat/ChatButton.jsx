import { MessageSquare } from 'lucide-react'

export default function ChatButton({ unread, open, onClick, buttonRef }) {
  const badge = unread > 9 ? '9+' : String(unread)
  const label = `${open ? 'Close' : 'Open'} chat${unread > 0 ? `, ${unread} unread` : ''}`
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-expanded={open}
      className="relative flex items-center gap-2 rounded border border-border px-2.5 py-1.5 text-sm font-medium text-text-muted transition-colors hover:border-accent/50 hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent motion-reduce:transition-none sm:px-3"
    >
      <MessageSquare className="h-4 w-4" aria-hidden="true" />
      <span className="hidden sm:inline">Chat</span>
      {unread > 0 && (
        <span
          aria-hidden="true"
          className="absolute -right-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-danger px-1 text-[11px] font-bold leading-none text-bg ring-2 ring-bg"
        >
          {badge}
        </span>
      )}
    </button>
  )
}
