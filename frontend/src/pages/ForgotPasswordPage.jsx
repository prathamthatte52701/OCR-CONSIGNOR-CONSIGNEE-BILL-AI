import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { authApi } from "../api/auth";

const MAX_NOTE = 200;

// Asks the admin to set a temporary password. The app sends no email: the admin tells the user
// the temporary password personally, and the user must choose a new one at the next login.
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const data = await authApi.requestPasswordReset({ email, note: note.trim() || null });
      setSent(data.message);
    } catch (err) {
      toast.error(err.userMessage || "Could not send the request.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 justify-center mb-6">
          <span className="h-2.5 w-2.5 rounded-full bg-accent" />
          <span className="font-semibold text-lg tracking-tight">THE MAIN OCR</span>
        </div>

        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h1 className="text-lg font-semibold">Forgot password</h1>
          {sent ? (
            <>
              <p role="status" className="rounded border border-accent/40 bg-accent/10 px-3 py-2 text-sm text-accent">
                {sent}
              </p>
              <p className="text-xs text-text-muted">
                The admin will give you a temporary password in person. No email is sent. Log in
                with it and choose your own password.
              </p>
            </>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-xs text-text-muted">
                Enter your account email. The admin gets a request and gives you a temporary
                password in person. No email is sent.
              </p>
              <div>
                <label className="text-xs text-text-muted block mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Note for the admin (optional)</label>
                <textarea
                  rows={2}
                  maxLength={MAX_NOTE}
                  value={note}
                  onChange={(e) => setNote(e.target.value.slice(0, MAX_NOTE))}
                  className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
                />
                <p className="text-right text-xs text-text-muted">
                  {note.length}/{MAX_NOTE}
                </p>
              </div>
              <button
                type="submit"
                disabled={busy}
                className="w-full bg-accent text-bg font-medium rounded py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
              >
                {busy ? "Sending..." : "Send request"}
              </button>
            </form>
          )}
          <div className="text-center text-xs text-text-muted">
            <Link to="/login" className="hover:text-accent">
              Back to login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
