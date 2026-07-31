import { useQuery } from "@tanstack/react-query";
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
  return useQuery({
    queryKey: ["document", id],
    queryFn: () => documentsApi.get(id),
    enabled: Boolean(id),
    refetchInterval: (query) => (POLL_STATUSES.has(query.state.data?.uploadStatus) ? 3000 : false),
  });
}
