import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Trash2, FileX2 } from "lucide-react";
import { adminApi } from "../api/admin";
import LoadingState from "../components/LoadingState";
import ConfirmModal from "../components/ConfirmModal";
import { formatIST } from "../lib/formatDate";

const DISPLAY_FIELDS = [
  "consigneeCode", "consignee", "consigneeAddress", "consigneeGstin", "consigneePan",
  "invoiceNo", "fiDoc", "challanDate", "reason",
  "consignorName", "consignorAddress", "consignorGstin", "consignorPan",
  "consignorPoNo", "requestNo", "irnNo",
  "totalBasicAmount", "totalAmount",
];

export default function AdminDocumentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState(null);
  const [editField, setEditField] = useState("");
  const [editValue, setEditValue] = useState("");
  const [confirmAction, setConfirmAction] = useState(null);

  useEffect(() => {
    adminApi.document(id).then(setDoc).catch((err) => toast.error(err.userMessage));
  }, [id]);

  const handleCorrect = async (e) => {
    e.preventDefault();
    if (!editField) return;
    try {
      await adminApi.correctDocument(id, editField, editValue || null);
      toast.success("Field updated.");
      setDoc((d) => ({ ...d, [editField]: editValue || null }));
      setEditField("");
      setEditValue("");
    } catch (err) {
      toast.error(err.userMessage || "Could not update field.");
    }
  };

  const handleDelete = async () => {
    try {
      await adminApi.deleteDocument(id);
      toast.success("Document permanently deleted.");
      navigate("/documents");
    } catch (err) {
      toast.error(err.userMessage || "Could not delete.");
    }
    setConfirmAction(null);
  };

  const handlePurge = async () => {
    try {
      await adminApi.purgeDocumentFiles(id);
      toast.success("Files deleted. Data preserved.");
      setDoc((d) => ({ ...d, part1FilePurged: true, part2FilePurged: true }));
    } catch (err) {
      toast.error(err.userMessage || "Could not delete files.");
    }
    setConfirmAction(null);
  };

  if (!doc) return <LoadingState message="Loading document..." />;

  return (
    <div className="max-w-3xl">
      <button onClick={() => navigate(-1)} className="text-xs text-text-muted hover:text-accent mb-3">
        &larr; Back
      </button>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">{doc.invoiceNo || "(no invoice no.)"}</h1>
          <p className="text-xs text-text-muted mt-1">
            Owner: {doc.ownerUsername} ({doc.ownerEmail}) &middot; Status: {doc.uploadStatus} &middot;{" "}
            {formatIST(doc.createdAt)}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setConfirmAction("purge")}
            disabled={doc.part1FilePurged && doc.part2FilePurged}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-warning/40 text-warning hover:bg-warning/10 disabled:opacity-40"
          >
            <FileX2 size={13} /> File Delete
          </button>
          <button
            onClick={() => setConfirmAction("delete")}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-danger/40 text-danger hover:bg-danger/10"
          >
            <Trash2 size={13} /> Delete
          </button>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3 mb-6">
        {DISPLAY_FIELDS.map((field) => (
          <div key={field} className="bg-surface border border-border rounded p-3">
            <p className="text-xs text-text-muted">{field}</p>
            <p className="text-sm font-mono truncate">{doc[field] ?? "-"}</p>
          </div>
        ))}
      </div>

      <form onSubmit={handleCorrect} className="bg-surface border border-border rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-semibold">Correct a field</h2>
        <div className="flex gap-2">
          <select
            value={editField}
            onChange={(e) => setEditField(e.target.value)}
            className="rounded border border-border bg-bg px-3 py-2 text-sm"
          >
            <option value="">Select field...</option>
            {DISPLAY_FIELDS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <input
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            placeholder="New value"
            className="flex-1 rounded border border-border bg-bg px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={!editField}
            className="bg-accent text-bg text-sm font-medium rounded px-4 py-2 disabled:opacity-40"
          >
            Save
          </button>
        </div>
      </form>

      <ConfirmModal
        open={confirmAction === "delete"}
        title="Permanently delete this document?"
        message="This permanently removes the document record and its original files. There is no undo."
        severity="critical"
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmModal
        open={confirmAction === "purge"}
        title="Permanently delete the original files?"
        message="Removes the stored Part 1 and Part 2 files. Extracted data is unaffected. This cannot be undone."
        severity="critical"
        confirmLabel="File Delete"
        onConfirm={handlePurge}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
}
