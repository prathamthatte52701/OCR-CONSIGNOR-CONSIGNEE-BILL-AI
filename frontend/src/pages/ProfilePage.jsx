import { useState } from "react";
import { toast } from "sonner";
import { authApi } from "../api/auth";
import { useAuthStore } from "../store/authStore";
import PasswordInput from "../components/PasswordInput";
import { useDialogStore } from "../store/dialogStore";
import { usePurgeAll } from "../hooks/useDocumentMutations";

const NUKE_PHRASE = "DELETE";

export default function ProfilePage() {
  const { username, email, role, token, setAuth } = useAuthStore();
  const [pwForm, setPwForm] = useState({ currentPassword: "", newPassword: "" });
  const [busy, setBusy] = useState(false);
  const [nukePassword, setNukePassword] = useState("");
  const confirm = useDialogStore((s) => s.confirm);
  const purgeAll = usePurgeAll();

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

  const handleNuke = async () => {
    if (!nukePassword) {
      toast.error("Enter your password to continue.");
      return;
    }
    const ok = await confirm({
      title: "Delete ALL your data?",
      message:
        "This permanently and irreversibly deletes every document and file you have ever uploaded. There is no undo, no recovery, no exceptions.",
      severity: "critical",
      confirmLabel: "Delete everything",
      requirePhrase: NUKE_PHRASE,
    });
    if (!ok) return;
    await purgeAll.mutateAsync({ password: nukePassword, confirmationPhrase: NUKE_PHRASE });
    setNukePassword("");
  };

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

      <div className="bg-danger/5 border border-danger/40 rounded-lg p-5 space-y-3">
        <h2 className="text-sm font-semibold text-danger">Danger zone</h2>
        <p className="text-xs text-text-muted">
          Permanently delete every document and file you own. This cannot be undone.
        </p>
        <PasswordInput
          placeholder="Confirm your password"
          value={nukePassword}
          onChange={(e) => setNukePassword(e.target.value)}
        />
        <button
          onClick={handleNuke}
          disabled={purgeAll.isPending}
          className="bg-danger text-white font-medium rounded px-4 py-2 text-sm hover:brightness-90 disabled:opacity-50"
        >
          {purgeAll.isPending ? "Deleting..." : "Delete all my data"}
        </button>
      </div>
    </div>
  );
}
