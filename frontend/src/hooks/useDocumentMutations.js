import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { documentsApi } from "../api/documents";

export function useUploadDocument() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: ({ part1, part2 }) => documentsApi.upload(part1, part2),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      toast.success("Upload received. Processing started.");
      navigate(`/documents/${data.id}`);
    },
    onError: (error) => toast.error(error.userMessage || "Upload failed."),
  });
}

export function useCorrectField(documentId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ field, value }) => documentsApi.correct(documentId, field, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document", documentId] });
      toast.success("Field updated.");
    },
    onError: (error) => toast.error(error.userMessage || "Could not save the field."),
  });
}

export function useReprocessDocument(documentId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => documentsApi.reprocess(documentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document", documentId] });
      toast.success("Reprocessing started.");
    },
    onError: (error) => toast.error(error.userMessage || "Could not reprocess."),
  });
}

export function useSoftDeleteDocument() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: (id) => documentsApi.softDelete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      toast.success("Document deleted.");
      navigate("/documents");
    },
    onError: (error) => toast.error(error.userMessage || "Could not delete."),
  });
}

export function usePurgeFiles(documentId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => documentsApi.purgeFiles(documentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["document", documentId] });
      toast.success("Original files purged. Extracted data was kept.");
    },
    onError: (error) => toast.error(error.userMessage || "Could not purge files."),
  });
}

export function usePurgeAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data) => documentsApi.purgeAll(data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      toast.success(data.message || "All data deleted.");
    },
    onError: (error) => toast.error(error.userMessage || "Could not complete the wipe."),
  });
}
