import { useState } from "react";
import { Link } from "react-router-dom";
import { useSignup } from "../hooks/useAuth";
import PasswordInput from "../components/PasswordInput";

export default function SignupPage() {
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const signup = useSignup();

  const handleSubmit = (e) => {
    e.preventDefault();
    signup.mutate(form);
  };

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 justify-center mb-6">
          <span className="h-2.5 w-2.5 rounded-full bg-accent" />
          <span className="font-semibold text-lg tracking-tight">THE MAIN OCR</span>
        </div>

        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h1 className="text-lg font-semibold">Create account</h1>

          <div>
            <label className="text-xs text-text-muted block mb-1">Username (3-8 chars)</label>
            <input
              required
              minLength={3}
              maxLength={8}
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

          <div>
            <label className="text-xs text-text-muted block mb-1">
              Password (8-64 characters, upper/lower/number/special, no spaces, not a common password)
            </label>
            <PasswordInput required value={form.password} onChange={update("password")} />
          </div>

          <button
            type="submit"
            disabled={signup.isPending}
            className="w-full bg-accent text-bg font-medium rounded py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
          >
            {signup.isPending ? "Creating..." : "Create account"}
          </button>

          <div className="text-center text-xs text-text-muted">
            Already have an account?{" "}
            <Link to="/login" className="hover:text-accent">
              Log in
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
