import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { authApi } from "../api/auth";
import PasswordInput from "../components/PasswordInput";

export default function ForgotPasswordPage() {
  const [step, setStep] = useState("verify");
  const [form, setForm] = useState({ username: "", email: "", newPassword: "" });
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleVerify = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await authApi.forgotPasswordVerify({ username: form.username, email: form.email });
      setStep("reset");
    } catch (err) {
      toast.error(err.userMessage || "Verification failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await authApi.forgotPasswordReset(form);
      toast.success("Password reset. Please log in.");
      navigate("/login");
    } catch (err) {
      toast.error(err.userMessage || "Reset failed.");
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

        {step === "verify" ? (
          <form onSubmit={handleVerify} className="bg-surface border border-border rounded-lg p-6 space-y-4">
            <h1 className="text-lg font-semibold">Forgot password</h1>
            <p className="text-xs text-text-muted">
              Enter your username and email exactly as used at signup.
            </p>
            <div>
              <label className="text-xs text-text-muted block mb-1">Username</label>
              <input
                required
                value={form.username}
                onChange={update("username")}
                className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-text-muted block mb-1">Email</label>
              <input
                type="email"
                required
                value={form.email}
                onChange={update("email")}
                className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full bg-accent text-bg font-medium rounded py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
            >
              {busy ? "Verifying..." : "Verify"}
            </button>
            <div className="text-center text-xs text-text-muted">
              <Link to="/login" className="hover:text-accent">
                Back to login
              </Link>
            </div>
          </form>
        ) : (
          <form onSubmit={handleReset} className="bg-surface border border-border rounded-lg p-6 space-y-4">
            <h1 className="text-lg font-semibold">Set a new password</h1>
            <PasswordInput
              required
              placeholder="New password"
              value={form.newPassword}
              onChange={update("newPassword")}
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full bg-accent text-bg font-medium rounded py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
            >
              {busy ? "Saving..." : "Reset password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
