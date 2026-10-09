import { useState } from "react";
import { toast } from "sonner";
import { adminAuthApi } from "../api/admin";
import { useAdminAuth } from "../context/AdminAuthContext";
import PasswordInput from "../components/PasswordInput";

export default function AdminProfilePage() {
  const { token, username, email, role, setAuth } = useAdminAuth();
  const [newUsername, setNewUsername] = useState(username || "");
  const [pwForm, setPwForm] = useState({ currentPassword: "", newPassword: "" });
  const [busy, setBusy] = useState(null);

  const saveUsername = async (e) => {
    e.preventDefault();
    setBusy("name");
    try {
      const data = await adminAuthApi.updateMe({ username: newUsername });
      setAuth({ token, username: data.username, email: data.email, role: data.role });
      toast.success("Username updated.");
    } catch (err) {
      toast.error(err.userMessage || "Could not update username.");
    } finally {
      setBusy(null);
    }
  };

  const changePassword = async (e) => {
    e.preventDefault();
    setBusy("password");
    try {
      const data = await adminAuthApi.changePassword(pwForm);
      setAuth({ token: data.token, username: data.username, email: data.email, role: data.role });
      toast.success("Password changed. Other sessions have been logged out.");
      setPwForm({ currentPassword: "", newPassword: "" });
    } catch (err) {
      toast.error(err.userMessage || "Could not change password.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="max-w-md space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Profile</h1>
        <p className="text-sm text-text-muted mt-1">
          {email} &middot; {role}
        </p>
      </div>

      <form onSubmit={saveUsername} className="bg-surface border border-border rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-semibold">Username</h2>
        <input
          required
          minLength={3}
          maxLength={8}
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
          className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy === "name"}
          className="bg-accent text-bg font-medium rounded px-4 py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
        >
          {busy === "name" ? "Saving..." : "Save username"}
        </button>
      </form>

      <form onSubmit={changePassword} className="bg-surface border border-border rounded-lg p-5 space-y-4">
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
          disabled={busy === "password"}
          className="bg-accent text-bg font-medium rounded px-4 py-2 text-sm hover:bg-accent-dim disabled:opacity-50"
        >
          {busy === "password" ? "Saving..." : "Change password"}
        </button>
      </form>
    </div>
  );
}
