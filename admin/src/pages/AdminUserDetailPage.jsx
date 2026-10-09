import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Trash2, AlertTriangle } from "lucide-react";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import ConfirmModal from "../components/ConfirmModal";
import NukeDialog from "../components/NukeDialog";
import { formatIST } from "../lib/formatDate";

const NUKE_USER_PHRASE = "NUKE USER";

export default function AdminUserDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [docs, setDocs] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [nukeOpen, setNukeOpen] = useState(false);
  const [nukeBusy, setNukeBusy] = useState(false);
  const [emailEditing, setEmailEditing] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [emailConfirmOpen, setEmailConfirmOpen] = useState(false);
  const [emailBusy, setEmailBusy] = useState(false);

  const load = () => {
    adminApi.user(id).then(setUser).catch((err) => toast.error(err.userMessage));
    adminApi.documents({ userId: id, page: 1, limit: 30 }).then(setDocs).catch(() => {});
  };

  useEffect(load, [id]);

  const handleRoleToggle = async () => {
    const newRole = user.role === "admin" ? "user" : "admin";
    try {
      const updated = await adminApi.updateUser(id, { role: newRole });
      setUser(updated);
      toast.success(`Role changed to ${newRole}.`);
    } catch (err) {
      toast.error(err.userMessage || "Could not update role.");
    }
  };

  const startEmailEdit = () => {
    setNewEmail(user.email);
    setEmailEditing(true);
  };

  const submitEmailForm = (e) => {
    e.preventDefault();
    const next = newEmail.trim().toLowerCase();
    if (next === user.email) {
      setEmailEditing(false); // nothing to change
      return;
    }
    setEmailConfirmOpen(true);
  };

  const handleEmailChange = async () => {
    setEmailConfirmOpen(false);
    setEmailBusy(true);
    try {
      const updated = await adminApi.updateUser(id, { email: newEmail.trim() });
      setUser(updated);
      setEmailEditing(false);
      toast.success("Email changed. The user was logged out everywhere.");
    } catch (err) {
      toast.error(err.userMessage || "Could not change the email.");
    } finally {
      setEmailBusy(false);
    }
  };

  const handleDelete = async () => {
    try {
      await adminApi.deleteUser(id);
      toast.success("User and all owned data deleted.");
      navigate("/users");
    } catch (err) {
      toast.error(err.userMessage || "Could not delete user.");
    }
    setConfirmOpen(false);
  };

  const handleNuke = async (payload) => {
    setNukeBusy(true);
    try {
      const data = await adminApi.nukeUser(id, payload);
      toast.success(data.message || "Documents deleted.");
      setNukeOpen(false);
      load();
    } catch (err) {
      toast.error(err.userMessage || "Could not complete the nuke.");
    } finally {
      setNukeBusy(false);
    }
  };

  if (!user) return <LoadingState message="Loading user..." />;

  return (
    <div className="max-w-2xl">
      <button onClick={() => navigate(-1)} className="text-xs text-text-muted hover:text-accent mb-3">
        &larr; Back
      </button>

      <div className="bg-surface border border-border rounded-lg p-5 mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-lg font-semibold">{user.username}</h1>
            <p className="text-sm text-text-muted">{user.email}</p>
            <p className="text-xs text-text-muted mt-1">Joined {formatIST(user.createdAt)}</p>
            {emailEditing ? (
              <form onSubmit={submitEmailForm} className="mt-3 flex items-center gap-2">
                <input
                  type="email"
                  required
                  autoFocus
                  aria-label="New email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="rounded border border-border bg-bg px-2 py-1 text-sm w-64"
                />
                <button
                  type="submit"
                  disabled={emailBusy}
                  className="text-xs px-3 py-1.5 rounded bg-accent text-bg font-medium disabled:opacity-50"
                >
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => setEmailEditing(false)}
                  className="text-xs px-3 py-1.5 rounded border border-border hover:bg-surface-raised"
                >
                  Cancel
                </button>
              </form>
            ) : (
              <button
                type="button"
                onClick={startEmailEdit}
                className="mt-2 text-xs text-accent hover:underline"
              >
                Change email
              </button>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className="text-xs px-2 py-0.5 rounded-full bg-accent/15 text-accent">{user.role}</span>
            <div className="flex gap-2">
              <button
                onClick={handleRoleToggle}
                className="text-xs px-3 py-1.5 rounded border border-border hover:bg-surface-raised"
              >
                Make {user.role === "admin" ? "user" : "admin"}
              </button>
              <button
                onClick={() => setConfirmOpen(true)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded border border-danger/40 text-danger hover:bg-danger/10"
              >
                <Trash2 size={12} /> Delete
              </button>
              <button
                onClick={() => setNukeOpen(true)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded border border-danger bg-danger/10 text-danger font-semibold hover:bg-danger/20"
              >
                <AlertTriangle size={12} /> Nuke this user
              </button>
            </div>
          </div>
        </div>
      </div>

      <h2 className="text-sm font-semibold text-text-muted mb-3">
        Documents ({docs?.total ?? "..."})
      </h2>
      <div className="space-y-2">
        {docs?.items.map((doc) => (
          <Link
            key={doc.id}
            to={`/documents/${doc.id}`}
            className="flex items-center justify-between bg-surface border border-border rounded-lg px-4 py-3 hover:border-accent/50"
          >
            <span className="text-sm">{doc.invoiceNo || "(no invoice no.)"}</span>
            <span className="text-xs text-text-muted">{doc.uploadStatus}</span>
          </Link>
        ))}
        {docs?.items.length === 0 && <p className="text-sm text-text-muted">No documents.</p>}
      </div>

      <ConfirmModal
        open={confirmOpen}
        title="Delete this user?"
        message={`This permanently deletes ${user.username} and every document/file they own. This cannot be undone.`}
        severity="critical"
        confirmLabel="Delete user"
        onConfirm={handleDelete}
        onCancel={() => setConfirmOpen(false)}
      />

      <ConfirmModal
        open={emailConfirmOpen}
        title="Change this user's email?"
        message={`${user.username} will be logged out everywhere and must log in with ${newEmail.trim().toLowerCase()} from now on. This is recorded in the audit log.`}
        severity="critical"
        confirmLabel="Change email"
        onConfirm={handleEmailChange}
        onCancel={() => setEmailConfirmOpen(false)}
      />

      <NukeDialog
        open={nukeOpen}
        title={`Nuke documents for ${user.username}?`}
        description={`This bulk-deletes this user's documents matching the range below. The user account itself is kept - only their documents (and originals) are removed. This cannot be undone.`}
        confirmationPhrase={NUKE_USER_PHRASE}
        confirmLabel="Nuke user's documents"
        busy={nukeBusy}
        onConfirm={handleNuke}
        onCancel={() => setNukeOpen(false)}
      />
    </div>
  );
}
