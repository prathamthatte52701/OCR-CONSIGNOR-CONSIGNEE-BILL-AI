import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { RefreshCw, Trash2, FileX2, Download, AlertTriangle, Layers } from "lucide-react";
import { useDocument } from "../hooks/useDocumentsQueries";
import {
  useCorrectField,
  useReprocessDocument,
  useDeleteDocument,
  usePurgeFiles,
} from "../hooks/useDocumentMutations";
import { useDialogStore } from "../store/dialogStore";
import { documentsApi } from "../api/documents";
import { readErrorMessage } from "../api/client";
import LoadingState from "../components/LoadingState";
import EditableField from "../components/EditableField";
import { formatIST } from "../lib/formatDate";

const CONSIGNEE_FIELDS = [
  ["consigneeCode", "Consignee Code"],
  ["consignee", "Consignee"],
  ["consigneeAddress", "Consignee Address"],
  ["consigneePincode", "Pincode"],
  ["consigneeStateCode", "State Code"],
  ["consigneeStateName", "State Name"],
  ["consigneeGstin", "GSTIN"],
  ["consigneePan", "PAN"],
  ["invoiceNo", "Invoice No"],
  ["fiDoc", "FI Doc."],
  ["challanDate", "Date"],
  ["reason", "Reason"],
];

const CONSIGNOR_FIELDS = [
  ["consignorName", "Name"],
  ["consignorAddress", "Address"],
  ["consignorPincode", "Pincode"],
  ["consignorStateCode", "State Code"],
  ["consignorStateName", "State Name"],
  ["consignorGstin", "GSTIN"],
  ["consignorPan", "PAN"],
  ["consignorPoNo", "PO No."],
  ["requestNo", "Request No."],
  ["irnNo", "IRN No."],
];

const SUMMARY_FIELDS = [
  ["totalBasicAmount", "Total Basic Amount"],
  ["cgstRate", "CGST Rate"],
  ["cgstAmount", "CGST Amount"],
  ["sgstRate", "SGST Rate"],
  ["sgstAmount", "SGST Amount"],
  ["igstRate", "IGST Rate"],
  ["igstAmount", "IGST Amount"],
  ["totalAmount", "Total Amount"],
];

const LINE_ITEM_FIELDS = [
  ["srNo", "Sr No"],
  ["description", "Description"],
  ["hsnSac", "HSN/SAC"],
  ["basic", "Basic"],
  ["quantity", "Quantity"],
  ["amount", "Amount"],
];

function FieldGrid({ fields, doc, onSave, disabled }) {
  return (
    <div className="grid sm:grid-cols-2 gap-4">
      {fields.map(([key, label]) => (
        <EditableField
          key={`${key}-${doc[key]}`}
          label={label}
          value={doc[key]}
          confidence={doc[`${key}Confidence`]}
          autoCorrected={doc[`${key}AutoCorrected`]}
          disabled={disabled}
          onSave={(value) => onSave(key, value)}
        />
      ))}
    </div>
  );
}

export default function DocumentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: doc, isLoading } = useDocument(id);
  const correctField = useCorrectField(id);
  const reprocess = useReprocessDocument(id);
  const deleteDocument = useDeleteDocument();
  const purgeFiles = usePurgeFiles(id);
  const confirm = useDialogStore((s) => s.confirm);

  if (isLoading) return <LoadingState message="Loading document..." />;
  if (!doc) return <p className="text-sm text-text-muted">Document not found.</p>;

  const editable = doc.uploadStatus === "processed" || doc.uploadStatus === "failed";
  const busy = doc.uploadStatus === "uploaded" || doc.uploadStatus === "processing";

  const saveField = (field, value) => correctField.mutateAsync({ field, value });
  const saveLineItem = (index, subfield, value) =>
    correctField.mutateAsync({ field: `lineItems.${index}.${subfield}`, value });

  const handleDownload = async (part) => {
    try {
      const { blob, filename } = await documentsApi.downloadFile(id, part);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(await readErrorMessage(err, "Could not download the file."));
    }
  };

  const handleReprocess = async () => {
    const ok = await confirm({
      title: "Reprocess this document?",
      message: "This re-runs OCR + AI extraction on the original files and overwrites all current field values, including any manual corrections.",
      severity: "warning",
      confirmLabel: "Reprocess",
    });
    if (ok) reprocess.mutate();
  };

  const handleDelete = async () => {
    const ok = await confirm({
      title: "Permanently delete this document?",
      message: "This permanently removes the document record and its original files. There is no undo.",
      severity: "critical",
      confirmLabel: "Delete",
    });
    if (ok) deleteDocument.mutate(id);
  };

  const handlePurgeFiles = async () => {
    const ok = await confirm({
      title: "Permanently delete original files?",
      message: "This permanently removes the stored Part 1 and Part 2 files to save space. Extracted data and field values are NOT affected and remain fully editable. This cannot be undone.",
      severity: "warning",
      confirmLabel: "File Delete",
    });
    if (ok) purgeFiles.mutate();
  };

  return (
    <div className="max-w-4xl">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div>
          <button onClick={() => navigate(-1)} className="text-xs text-text-muted hover:text-accent mb-1">
            &larr; Back
          </button>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            {doc.invoiceNo || "(no invoice no.)"}
            {doc.hasLowConfidenceFields && <AlertTriangle size={16} className="text-warning" />}
            {doc.multiPage && <Layers size={16} className="text-text-muted" />}
          </h1>
          <p className="text-xs text-text-muted mt-1">
            Status: <span className="font-medium">{doc.uploadStatus}</span> &middot; Uploaded{" "}
            {formatIST(doc.createdAt)}
            {doc.reprocessedAt && <> &middot; Reprocessed {formatIST(doc.reprocessedAt)}</>}
          </p>
          {doc.processingError && (
            <p className="text-xs text-danger mt-1">Error: {doc.processingError}</p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {["part1", "part2"].map(
            (part) =>
              !doc[`${part}FilePurged`] && (
                <button
                  key={part}
                  onClick={() => handleDownload(part)}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-border hover:bg-surface-raised"
                >
                  <Download size={13} /> {part === "part1" ? "Part 1" : "Part 2"}
                </button>
              )
          )}
          <button
            onClick={handleReprocess}
            disabled={busy || doc.part1FilePurged || doc.part2FilePurged}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-border hover:bg-surface-raised disabled:opacity-40"
          >
            <RefreshCw size={13} /> Reprocess
          </button>
          <button
            onClick={handlePurgeFiles}
            disabled={doc.part1FilePurged && doc.part2FilePurged}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-warning/40 text-warning hover:bg-warning/10 disabled:opacity-40"
          >
            <FileX2 size={13} /> File Delete
          </button>
          <button
            onClick={handleDelete}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-danger/40 text-danger hover:bg-danger/10"
          >
            <Trash2 size={13} /> Delete
          </button>
        </div>
      </div>

      {busy && <LoadingState message="Extracting fields - this page updates automatically..." />}

      {!busy && (
        <div className="space-y-8">
          <section>
            <h2 className="text-sm font-semibold text-text-muted mb-3">Consignee</h2>
            <FieldGrid fields={CONSIGNEE_FIELDS} doc={doc} onSave={saveField} disabled={!editable} />
          </section>

          <section>
            <h2 className="text-sm font-semibold text-text-muted mb-3">Consignor</h2>
            <FieldGrid fields={CONSIGNOR_FIELDS} doc={doc} onSave={saveField} disabled={!editable} />
          </section>

          <section>
            <h2 className="text-sm font-semibold text-text-muted mb-3">Line Items</h2>
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-surface-raised text-left text-xs text-text-muted">
                    {LINE_ITEM_FIELDS.map(([key, label]) => (
                      <th key={key} className="px-3 py-2 font-medium whitespace-nowrap">
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(doc.lineItems || []).map((item, index) => (
                    <tr key={index} className="border-t border-border">
                      {LINE_ITEM_FIELDS.map(([key]) => (
                        <td key={key} className="px-2 py-2 min-w-[120px]">
                          <EditableField
                            key={`${index}-${key}-${item[key]}`}
                            label=""
                            value={item[key]}
                            confidence={item[`${key}Confidence`]}
                            autoCorrected={item[`${key}AutoCorrected`]}
                            disabled={!editable}
                            onSave={(value) => saveLineItem(index, key, value)}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                  {(doc.lineItems || []).length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-6 text-center text-text-muted text-sm">
                        No line items extracted.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-sm font-semibold text-text-muted mb-3">Tax Summary</h2>
            <FieldGrid fields={SUMMARY_FIELDS} doc={doc} onSave={saveField} disabled={!editable} />
          </section>
        </div>
      )}
    </div>
  );
}
