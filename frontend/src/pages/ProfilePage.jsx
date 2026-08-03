import { useState } from "react";
import { toast } from "sonner";
import { authApi } from "../api/auth";
import { useAuthStore } from "../store/authStore";
import PasswordInput from "../components/PasswordInput";

export default function ProfilePage() {
  const { username, email, role, token, setAuth } = useAuthStore();
  const [pwForm, setPwForm] = useState({ currentPassword: "", newPassword: "" });
  const [busy, setBusy] = useState(false);

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const data = await authApi.changePassword(pwForm);
      setAuth({ token: data.token, username: data.username, email: data.email, role: data.role });
      toast.success("Password changed. Other sessions have been logged out.");
      setPwForm({ currentPassword: "", newPassword: "" });
    } catch (err) {
      toast.error(err.userMessage || "Could not change password.");
    } finally {
      setBusy(false);
    }
  };

  if (!token) return null;

  return (
    <div className="max-w-md space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Profile</h1>
        <p className="text-sm text-text-muted mt-1">
          {username} &middot; {email} &middot; {role}
        </p>
      </div>

      <form onSubmit={handleChangePassword} className="bg-surface border border-border rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-semibold">Change password</h2>
        <div>
          <label className="text-xs text-text-muted block mb-1">Current password</label>
          <PasswordInput
            required
            value={pwForm.currentPassword}
            onChange={(e) => setPwForm((f) => ({ ...f, currentPassword: e.target.value }))}
          />
        </div>
        <div>
          <label className="text-xs text-text-muted block mb-1">New password</label>
          <PasswordInput
            required
            value={pwForm.newPassword}
            onChange={(e) => setPwForm((f) => ({ ...f, newPassword: e.target.value }))}
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="bg-accent text-bg font-medium rounded px-4 py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
        >
          {busy ? "Saving..." : "Change password"}
        </button>
      </form>
    </div>
  );
}
