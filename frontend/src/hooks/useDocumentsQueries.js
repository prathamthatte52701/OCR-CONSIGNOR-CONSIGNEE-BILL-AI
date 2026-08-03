import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { documentsApi } from "../api/documents";

const POLL_STATUSES = new Set(["uploaded", "processing"]);

export function useDocumentsList(params) {
  return useQuery({
    queryKey: ["documents", params],
    queryFn: () => documentsApi.list(params),
  });
}

export function useDocumentStats() {
  return useQuery({
    queryKey: ["documents", "stats"],
    queryFn: () => documentsApi.stats(),
  });
}

export function useDocument(id) {
  const query = useQuery({
    queryKey: ["document", id],
    queryFn: () => documentsApi.get(id),
    enabled: Boolean(id),
    refetchInterval: (query) => (POLL_STATUSES.has(query.state.data?.uploadStatus) ? 3000 : false),
  });

  const prevStatusRef = useRef(undefined);
  const prevIdRef = useRef(id);
  useEffect(() => {
    if (prevIdRef.current !== id) {
      prevIdRef.current = id;
      prevStatusRef.current = undefined;
    }
    const status = query.data?.uploadStatus;
    if (status === undefined) return;
    const wasProcessing = POLL_STATUSES.has(prevStatusRef.current);
    if (wasProcessing && status === "processed") {
      toast.success("Document processed successfully.");
    } else if (wasProcessing && status === "failed") {
      toast.error(query.data.processingError || "Document processing failed.");
    }
    prevStatusRef.current = status;
  }, [id, query.data?.uploadStatus, query.data?.processingError]);

  return query;
}
