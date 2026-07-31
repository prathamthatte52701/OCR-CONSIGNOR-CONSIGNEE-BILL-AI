import { client } from "./client";

export const documentsApi = {
  upload: (part1File, part2File) => {
    const form = new FormData();
    form.append("part1", part1File);
    form.append("part2", part2File);
    return client.post("/documents/upload", form).then((r) => r.data);
  },
  list: (params) => client.get("/documents", { params }).then((r) => r.data),
  stats: () => client.get("/documents/stats").then((r) => r.data),
  get: (id) => client.get(`/documents/${id}`).then((r) => r.data),
  correct: (id, field, value) =>
    client.patch(`/documents/${id}/correct`, { field, value }).then((r) => r.data),
  reprocess: (id) => client.post(`/documents/${id}/reprocess`).then((r) => r.data),
  softDelete: (id) => client.delete(`/documents/${id}`).then((r) => r.data),
  purgeFiles: (id) => client.post(`/documents/${id}/purge-files`).then((r) => r.data),
  purgeRangePreview: (params) =>
    client.get("/documents/purge-range/preview", { params }).then((r) => r.data),
  purgeRange: (data) => client.delete("/documents/purge-range", { data }).then((r) => r.data),
  purgeAll: (data) => client.delete("/documents/purge-all", { data }).then((r) => r.data),
  downloadUrl: (id, part) => `/api/documents/${id}/download/${part}`,
};
