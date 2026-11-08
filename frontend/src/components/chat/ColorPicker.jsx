import { CHAT_COLORS } from '../../utils/chatColors'

export default function ColorPicker({ value, onChange, failed }) {
  return (
    <div className="border-b border-border bg-surface-raised px-4 py-3">
      <p id="chat-color-label" className="mb-2 text-xs font-semibold text-text-muted">Your message colour</p>
      <div role="radiogroup" aria-labelledby="chat-color-label" className="flex flex-wrap gap-2">
        {CHAT_COLORS.map((c) => (
          <label key={c.id} className="cursor-pointer">
            <input
              type="radio"
              name="chat-color"
              value={c.id}
              checked={value === c.id}
              onChange={() => onChange(c.id)}
              className="peer sr-only"
            />
            <span className="sr-only">{c.label}</span>
            <span
              aria-hidden="true"
              title={c.label}
              style={{ backgroundColor: c.bubble }}
              className="block h-7 w-7 rounded-full ring-offset-2 ring-offset-surface-raised peer-checked:ring-2 peer-checked:ring-white peer-focus-visible:ring-2 peer-focus-visible:ring-accent"
            />
          </label>
        ))}
      </div>
      {failed && <p role="alert" className="mt-2 text-xs text-danger">Could not save your colour.</p>}
    </div>
  )
}
