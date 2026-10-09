import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShieldAlert } from "lucide-react";
import { adminAuthApi } from "../api/admin";
import { useAdminAuth } from "../context/AdminAuthContext";

export default function AdminLoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { setAuth } = useAdminAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const data = await adminAuthApi.login({ email, password });
      if (data.role !== "admin") {
        toast.error("This account does not have admin access.");
        return;
      }
      setAuth(data);
      navigate("/dashboard");
    } catch (err) {
      toast.error(err.userMessage || "Login failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 justify-center mb-6">
          <ShieldAlert className="text-accent" size={20} />
          <span className="font-semibold text-lg tracking-tight">THE MAIN OCR Admin</span>
        </div>

        <form onSubmit={handleSubmit} className="bg-surface border border-border rounded-lg p-6 space-y-4">
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
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="w-full bg-accent text-bg font-medium rounded py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
          >
            {busy ? "Logging in..." : "Log in"}
          </button>
          <div className="text-center text-xs text-text-muted">
            <Link to="/forgot-password" className="hover:text-accent">
              Forgot password?
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
