import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { authApi } from "../api/auth";
import { useAuthStore } from "../store/authStore";
import PasswordInput from "../components/PasswordInput";
import { useLogout } from "../hooks/useAuth";

// Shown (by RequireAuth) for every route while an admin-set temporary password is in force.
// Logging out is the only other action.
export default function SetNewPasswordPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const setMustChangePassword = useAuthStore((s) => s.setMustChangePassword);
  const logout = useLogout();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (next !== confirm) {
      setError("New password and confirmation do not match.");
      return;
    }
    if (next === current) {
      setError("The new password must be different from the temporary password.");
      return;
    }
    setBusy(true);
    try {
      const data = await authApi.changePassword({ currentPassword: current, newPassword: next });
      // The old tokens were revoked: keep the fresh one and leave the forced-change mode.
      setAuth({ token: data.token, username: data.username, email: data.email, role: data.role });
      setMustChangePassword(false);
      toast.success("Password changed.");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err.userMessage || "Could not change your password. Please try again.");
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

        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h1 className="text-lg font-semibold">Set a new password</h1>
          <p className="text-xs text-text-muted">
            The admin gave you a temporary password. Choose your own to continue.
          </p>

          <div>
            <label className="text-xs text-text-muted block mb-1">Temporary password</label>
            <PasswordInput
              required
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">New password</label>
            <PasswordInput
              required
              minLength={8}
              maxLength={64}
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
            <p className="mt-1 text-[11px] text-text-muted">
              8-64 characters with uppercase, lowercase, a number and a special character, no spaces.
            </p>
          </div>
          <div>
            <label className="text-xs text-text-muted block mb-1">Confirm new password</label>
            <PasswordInput
              required
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>

          {error && (
            <p role="alert" className="rounded border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full bg-accent text-bg font-medium rounded py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
          >
            {busy ? "Saving..." : "Set new password"}
          </button>
          <button type="button" onClick={logout} className="block w-full text-center text-xs text-text-muted hover:text-accent">
            Log out
          </button>
        </form>
      </div>
    </div>
  );
}
