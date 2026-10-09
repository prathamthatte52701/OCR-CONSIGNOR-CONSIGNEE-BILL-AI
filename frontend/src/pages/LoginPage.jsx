import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useLogin } from "../hooks/useAuth";
import PasswordInput from "../components/PasswordInput";

// Fixed texts only - the notice comes from a URL key, never from free text in the URL.
const NOTICES = {
  signup: { tone: "info", text: "Account created. Waiting for admin approval." },
  pending: { tone: "warn", text: "Waiting for admin approval." },
  rejected: { tone: "danger", text: "Your request was not approved. Contact the admin." },
};

const TONE_CLASSES = {
  info: "border-accent/40 bg-accent/10 text-accent",
  warn: "border-warning/40 bg-warning/10 text-warning",
  danger: "border-danger/40 bg-danger/10 text-danger",
};

function loginNotice(login, searchParams) {
  if (login.error?.response?.status === 403) {
    const detail = login.error.response.data?.detail;
    if (detail === NOTICES.pending.text) return NOTICES.pending;
    if (detail === NOTICES.rejected.text) return NOTICES.rejected;
  }
  return NOTICES[searchParams.get("notice")] ?? null;
}

export default function LoginPage() {
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();

  const handleSubmit = (e) => {
    e.preventDefault();
    login.mutate({ email, password });
  };

  const notice = loginNotice(login, searchParams);

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 justify-center mb-6">
          <span className="h-2.5 w-2.5 rounded-full bg-accent" />
          <span className="font-semibold text-lg tracking-tight">THE MAIN OCR</span>
        </div>

        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h1 className="text-lg font-semibold">Log in</h1>

          {notice && (
            <p role="alert" className={`rounded border px-3 py-2 text-sm ${TONE_CLASSES[notice.tone]}`}>
              {notice.text}
            </p>
          )}

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
            <label className="text-xs text-text-muted block mb-1">Password</label>
            <PasswordInput required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>

          <button
            type="submit"
            disabled={login.isPending}
            className="w-full bg-accent text-bg font-medium rounded py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
          >
            {login.isPending ? "Logging in..." : "Log in"}
          </button>

          <div className="flex justify-between text-xs text-text-muted">
            <Link to="/forgot-password" className="hover:text-accent">
              Forgot password?
            </Link>
            <Link to="/signup" className="hover:text-accent">
              Create account
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
