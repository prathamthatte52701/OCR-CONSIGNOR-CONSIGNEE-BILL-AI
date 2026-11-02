import { useQuery } from "@tanstack/react-query";
import { documentsApi } from "../api/documents";

const TYPE_BY_EXT = { pdf: "application/pdf", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg" };

// Fetches one original through the existing authenticated download route and returns a File
// (name + type) for the viewer. Cached for the session of the page; a 4xx is never retried.
export function useDocumentFile(id, part, enabled, mimeType) {
  return useQuery({
    queryKey: ["documentFile", id, part],
    enabled: Boolean(id) && enabled,
    staleTime: Infinity,
    gcTime: 5 * 60 * 1000,
    retry: (count, error) => {
      const status = error?.response?.status;
      return !(status >= 400 && status < 500) && count < 2;
    },
    queryFn: async () => {
      const { blob, filename } = await documentsApi.downloadFile(id, part);
      const ext = filename.split(".").pop()?.toLowerCase();
      const type = (blob.type && blob.type !== "application/octet-stream" ? blob.type : null) || mimeType || TYPE_BY_EXT[ext] || "";
      return new File([blob], filename, { type });
    },
  });
}
